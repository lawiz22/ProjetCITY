const cityAnnotationPlugin = {
    id: 'cityAnnotationBands',
    beforeDraw(chart, _args, pluginOptions) {
        const annotations = pluginOptions?.annotations || [];
        const xScale = chart.scales.x;
        const chartArea = chart.chartArea;
        const labels = chart.data.labels || [];
        if (!xScale || !chartArea || annotations.length === 0) {
            chart.$annotationBands = [];
            return;
        }

        const context = chart.ctx;
        chart.$annotationBands = [];
        context.save();

        annotations.forEach((annotation, index) => {
            const isFlashing = Number(annotation.flashUntil || 0) > Date.now();
            const labelIndex = labels.findIndex((label) => Number(label) === Number(annotation.year));
            if (labelIndex < 0) {
                return;
            }
            const center = xScale.getPixelForValue(labelIndex);
            const previous = labelIndex > 0 ? xScale.getPixelForValue(labelIndex - 1) : center - 20;
            const next = labelIndex < labels.length - 1 ? xScale.getPixelForValue(labelIndex + 1) : center + 20;
            const width = Math.max(8, Math.min(28, Math.abs(next - previous) * 0.46));
            const left = center - width / 2;
            context.save();
            context.globalAlpha = 0.16;
            context.fillStyle = annotation.color;
            context.fillRect(left, chartArea.top, width, chartArea.bottom - chartArea.top);
            context.restore();
            context.strokeStyle = annotation.color;
            context.lineWidth = isFlashing ? 5 : annotation.active ? 3 : 1;
            context.strokeRect(left, chartArea.top, width, chartArea.bottom - chartArea.top);
            if (isFlashing) {
                context.save();
                context.globalAlpha = 0.2;
                context.fillStyle = annotation.color;
                context.fillRect(left - 3, chartArea.top, width + 6, chartArea.bottom - chartArea.top);
                context.restore();
            }
            if (index < 6) {
                context.save();
                context.translate(left + width / 2, chartArea.top + 18);
                context.rotate(-Math.PI / 2);
                context.fillStyle = annotation.color;
                context.font = '12px Space Grotesk';
                context.textAlign = 'center';
                context.fillText(`${annotation.year}`, 0, 0);
                context.restore();
            }
            chart.$annotationBands.push({
                ...annotation,
                left,
                right: left + width,
                top: chartArea.top,
                bottom: chartArea.bottom,
            });
        });

        context.restore();
    }
};

const mountedCharts = [];

function getThemePalette() {
    const styles = getComputedStyle(document.documentElement);
    return {
        ink: styles.getPropertyValue('--ink').trim() || '#1b2430',
        muted: styles.getPropertyValue('--muted').trim() || '#5b6574',
        line: styles.getPropertyValue('--line').trim() || 'rgba(27, 36, 48, 0.08)',
    };
}

function applyThemeToChart(chart) {
    const palette = getThemePalette();
    if (chart.options?.plugins?.legend?.labels) {
        chart.options.plugins.legend.labels.color = palette.ink;
    }
    if (chart.options?.scales?.x) {
        chart.options.scales.x.ticks.color = palette.muted;
        chart.options.scales.x.grid.color = palette.line;
    }
    if (chart.options?.scales?.y) {
        chart.options.scales.y.ticks.color = palette.muted;
        chart.options.scales.y.grid.color = palette.line;
    }
    chart.update('none');
}

function buildDefaultOptions(chartType) {
    const palette = getThemePalette();
    const base = {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: {
            legend: {
                labels: {
                    color: palette.ink,
                    font: {
                        family: 'Space Grotesk'
                    }
                }
            }
        },
        scales: {
            x: {
                ticks: {
                    color: palette.muted,
                    autoSkip: true,
                    maxTicksLimit: chartType === 'line' ? 12 : 10,
                    maxRotation: 0,
                    minRotation: 0
                },
                grid: { color: palette.line }
            },
            y: {
                ticks: {
                    color: palette.muted,
                    maxTicksLimit: 8
                },
                grid: { color: palette.line }
            }
        }
    };

    if (chartType === 'line') {
        base.elements = {
            line: { tension: 0.28, borderWidth: 3 },
            point: { radius: 0, hoverRadius: 5 }
        };
        base.interaction = {
            intersect: false,
            mode: 'nearest'
        };
        base.plugins.zoom = {
            limits: {
                x: { minRange: 5 }
            },
            pan: {
                enabled: true,
                mode: 'x',
                modifierKey: 'shift'
            },
            zoom: {
                wheel: { enabled: true },
                pinch: { enabled: true },
                drag: {
                    enabled: true,
                    backgroundColor: 'rgba(38, 70, 83, 0.12)',
                    borderColor: 'rgba(38, 70, 83, 0.42)',
                    borderWidth: 1
                },
                mode: 'x'
            }
        };
        base.plugins.cityAnnotationBands = {
            annotations: []
        };
    }

    return base;
}

function sanitizeFilename(value) {
    return (value || 'chart')
        .toString()
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9-_]+/g, '-')
        .replace(/-+/g, '-')
        .replace(/^-|-$/g, '') || 'chart';
}

function downloadChart(chart, filename) {
    const link = document.createElement('a');
    link.href = chart.toBase64Image('image/png', 1);
    link.download = `${sanitizeFilename(filename)}.png`;
    link.click();
}

function getVisibleAnnotations(annotations, state) {
    return annotations.filter((annotation) => state.visibleIds.has(annotation.id));
}

function syncAnnotationCards(chartScope, visibleIds, activeId) {
    chartScope.querySelectorAll('[data-annotation-card]').forEach((card) => {
        const annotationId = card.dataset.annotationId;
        const isVisible = visibleIds.has(annotationId);
        card.classList.toggle('is-active', isVisible && annotationId === activeId);
        card.classList.toggle('is-muted', !isVisible);
    });
}

function getLinkedYearsFromCard(card) {
    return (card?.dataset.linkedYears || '')
        .split(',')
        .map((value) => value.trim())
        .filter(Boolean);
}

function getSelectedPeriodYears(chartScope, selectedPeriodId) {
    if (!selectedPeriodId) {
        return [];
    }
    const card = chartScope.querySelector(`[data-period-card][data-period-id="${selectedPeriodId}"]`);
    return getLinkedYearsFromCard(card);
}

function syncAnnotationFilters(chartScope, visibleIds) {
    chartScope.querySelectorAll('[data-annotation-toggle]').forEach((toggle) => {
        const annotationId = toggle.dataset.annotationId;
        const isVisible = visibleIds.has(annotationId);
        toggle.checked = isVisible;
    });

    chartScope.querySelectorAll('[data-annotation-list-item]').forEach((item) => {
        const annotationId = item.dataset.annotationId;
        item.classList.toggle('is-muted', !visibleIds.has(annotationId));
    });
}

function syncAnnotationCounter(chartScope, visibleCount, totalCount) {
    const counter = chartScope.querySelector('[data-annotation-visible-count]');
    if (!counter) {
        return;
    }
    if (visibleCount === totalCount) {
        counter.textContent = `${visibleCount} annotation(s) visible(s)`;
        return;
    }
    counter.textContent = `${visibleCount} annotation(s) visible(s) sur ${totalCount}`;
}

function setChartFocusIndicator(chartScope, text) {
    const indicator = chartScope.querySelector('[data-chart-focus-indicator]');
    if (!indicator) {
        return;
    }
    indicator.textContent = text || 'Vue complète active';
    indicator.classList.toggle('is-focused', text && text !== 'Vue complète active');
}

function syncTimelineHighlights(chartScope, activeAnnotation) {
    const activeYear = activeAnnotation ? String(activeAnnotation.year) : null;
    chartScope.querySelectorAll('[data-period-card]').forEach((card) => {
        const linkedYears = getLinkedYearsFromCard(card);
        card.classList.toggle('is-active', Boolean(activeYear) && linkedYears.includes(activeYear));
    });

    chartScope.querySelectorAll('[data-annotation-year-target]').forEach((chip) => {
        chip.classList.toggle('is-active', Boolean(activeYear) && String(chip.dataset.annotationYearTarget) === activeYear);
    });
}

function syncPeriodSelection(chartScope, selectedPeriodId) {
    const selectedYears = getSelectedPeriodYears(chartScope, selectedPeriodId);
    const hasSelection = Boolean(selectedPeriodId);

    const timeline = chartScope.querySelector('.period-timeline');
    if (timeline) {
        timeline.classList.toggle('has-period-selection', hasSelection);
    }

    chartScope.querySelectorAll('[data-period-card]').forEach((card) => {
        card.classList.toggle('is-period-selected', card.dataset.periodId === selectedPeriodId);
    });

    chartScope.querySelectorAll('[data-annotation-card]').forEach((card) => {
        const year = String(card.dataset.annotationYear || '');
        card.classList.toggle('is-related', hasSelection && selectedYears.includes(year));
        card.classList.toggle('is-unrelated', hasSelection && !selectedYears.includes(year));
    });

    chartScope.querySelectorAll('[data-annotation-year-target]').forEach((chip) => {
        const year = String(chip.dataset.annotationYearTarget || '');
        chip.classList.toggle('is-related', hasSelection && selectedYears.includes(year));
        chip.classList.toggle('is-unrelated', hasSelection && !selectedYears.includes(year));
    });

}

function triggerTimelineFocus(chart, chartScope, annotations, annotation, periodId) {
    if (annotation) {
        annotation.flashUntil = Date.now() + 1200;
        chart.update('none');
        window.setTimeout(() => {
            annotation.flashUntil = 0;
            chart.update('none');
        }, 1250);
    }

    if (periodId) {
        const periodCard = chartScope.querySelector(`[data-period-card][data-period-id="${periodId}"]`);
        if (periodCard) {
            periodCard.classList.remove('is-focus-flash');
            void periodCard.offsetWidth;
            periodCard.classList.add('is-focus-flash');
            window.setTimeout(() => {
                periodCard.classList.remove('is-focus-flash');
            }, 1250);
        }
    }
}

function resetChartView(chart) {
    if (chart.options?.scales?.x) {
        delete chart.options.scales.x.min;
        delete chart.options.scales.x.max;
    }
    if (typeof chart.resetZoom === 'function') {
        chart.resetZoom();
    } else {
        chart.update();
    }
}

function clearAllFocus(chart, chartBlock, chartScope, annotations, state) {
    if (state.autoplayTimer) {
        window.clearInterval(state.autoplayTimer);
        state.autoplayTimer = null;
    }
    annotations.forEach((annotation) => {
        annotation.flashUntil = 0;
    });
    state.visibleIds = new Set(annotations.map((annotation) => annotation.id));
    state.activeId = null;
    state.selectedPeriodId = null;
    state.guidedIndex = null;
    applyAnnotationState(chart, chartBlock, chartScope, annotations, state);
    resetChartView(chart);
    setChartFocusIndicator(chartScope, 'Vue complète active');
    syncGuidedReaderStatus(chartScope, annotations, state);
}

function syncGuidedReaderStatus(chartScope, annotations, state) {
    const status = chartScope.querySelector('[data-guided-reader-status]');
    const autoplayButton = chartScope.querySelector('[data-guided-autoplay]');
    if (autoplayButton) {
        autoplayButton.textContent = state.autoplayTimer ? '||' : '>>';
        autoplayButton.setAttribute('aria-label', state.autoplayTimer ? 'Arreter l\'autoplay' : 'Activer l\'autoplay');
        autoplayButton.setAttribute('title', state.autoplayTimer ? 'Arreter l\'autoplay' : 'Activer l\'autoplay');
    }
    if (!status) {
        return;
    }
    if (state.guidedIndex === null || state.guidedIndex === undefined) {
        status.textContent = state.autoplayTimer ? 'Autoplay actif' : 'Lecture libre';
        return;
    }
    status.textContent = `${state.autoplayTimer ? 'Autoplay' : 'Lecture guidée'} ${state.guidedIndex + 1}/${state.periodCards.length}`;
}

function focusPeriodCard(chart, chartBlock, chartScope, annotations, state, periodCard, options = {}) {
    if (!periodCard) {
        return;
    }
    const periodId = periodCard.dataset.periodId || null;
    const linkedYears = getLinkedYearsFromCard(periodCard);
    const onlyLinked = Boolean(options.onlyLinked);
    const shouldZoom = options.zoom !== false;
    const primaryYear = periodCard.dataset.periodPrimaryYear || linkedYears[0] || '';
    const primaryAnnotation = primaryYear
        ? annotations.find((item) => String(item.year) === String(primaryYear))
        : null;

    state.selectedPeriodId = periodId;
    if (onlyLinked) {
        state.visibleIds = new Set(
            annotations
                .filter((item) => linkedYears.includes(String(item.year)))
                .map((item) => item.id)
        );
    }

    if (primaryAnnotation) {
        state.visibleIds.add(primaryAnnotation.id);
        setActiveAnnotation(chart, chartBlock, chartScope, annotations, state, primaryAnnotation);
        if (shouldZoom) {
            zoomToAnnotation(chart, primaryAnnotation);
        }
        triggerTimelineFocus(chart, chartScope, annotations, primaryAnnotation, periodId);
        setChartFocusIndicator(chartScope, `Focus timeline: ${periodCard.querySelector('.timeline-header strong')?.textContent || primaryAnnotation.label}`);
    } else {
        applyAnnotationState(chart, chartBlock, chartScope, annotations, state);
        triggerTimelineFocus(chart, chartScope, annotations, null, periodId);
        setChartFocusIndicator(chartScope, `Focus timeline: ${periodCard.querySelector('.timeline-header strong')?.textContent || 'période active'}`);
    }

    periodCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
    syncGuidedReaderStatus(chartScope, annotations, state);
}

function applyAnnotationState(chart, chartBlock, chartScope, annotations, state) {
    const visibleAnnotations = getVisibleAnnotations(annotations, state);
    chart.options.plugins.cityAnnotationBands.annotations = visibleAnnotations;
    if (state.activeId && !state.visibleIds.has(state.activeId)) {
        state.activeId = null;
    }

    syncAnnotationCards(chartScope, state.visibleIds, state.activeId);
    syncAnnotationFilters(chartScope, state.visibleIds);
    syncAnnotationCounter(chartScope, visibleAnnotations.length, annotations.length);

    const activeAnnotation = visibleAnnotations.find((annotation) => annotation.id === state.activeId) || null;
    syncTimelineHighlights(chartScope, activeAnnotation);
    syncPeriodSelection(chartScope, state.selectedPeriodId);
    chart.update('none');
}

function setActiveAnnotation(chart, chartBlock, chartScope, annotations, state, annotation) {
    state.activeId = annotation ? annotation.id : null;
    applyAnnotationState(chart, chartBlock, chartScope, annotations, state);
}

function activateAnnotationCard(chartBlock, annotation) {
    if (!chartBlock) {
        return;
    }
    chartBlock.querySelectorAll('[data-annotation-card]').forEach((card) => {
        card.classList.toggle('is-active', card.dataset.annotationYear === String(annotation?.year || ''));
    });
}

function zoomToAnnotation(chart, annotation) {
    if (!annotation) {
        return;
    }
    const labels = chart.data?.labels || [];
    const targetIndex = labels.findIndex((label) => Number(label) === Number(annotation.year));
    if (targetIndex < 0 || !chart.options?.scales?.x) {
        return;
    }
    const windowRadius = Math.max(2, Math.min(6, Math.round(labels.length * 0.08)));
    chart.options.scales.x.min = Math.max(0, targetIndex - windowRadius);
    chart.options.scales.x.max = Math.min(labels.length - 1, targetIndex + windowRadius);
    if (typeof chart.update === 'function') {
        chart.update('none');
    }
}

function jumpToPeriodForAnnotation(chartScope, year) {
    const periodCards = Array.from(chartScope.querySelectorAll('[data-period-card]'));
    const targetCard = periodCards.find((card) => getLinkedYearsFromCard(card).includes(String(year)));
    if (!targetCard) {
        return;
    }

    targetCard.classList.remove('is-focus-flash');
    void targetCard.offsetWidth;
    targetCard.classList.add('is-focus-flash');
    targetCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
    window.setTimeout(() => {
        targetCard.classList.remove('is-focus-flash');
    }, 1250);
}

function mountChart(canvas) {
    const rawPayload = canvas.dataset.chart;
    if (!rawPayload) {
        return;
    }

    const payload = JSON.parse(rawPayload);
    const chartType = canvas.dataset.chartType || 'bar';
    const context = canvas.getContext('2d');
    const chartBlock = canvas.closest('.chart-block');
    const chartScope = canvas.closest('.main-panel') || document;
    const filename = canvas.dataset.chartFilename || document.title || 'chart';
    const annotations = Array.isArray(payload.annotations) ? payload.annotations : [];
    const annotationState = {
        visibleIds: new Set(annotations.map((annotation) => annotation.id)),
        activeId: null,
        selectedPeriodId: null,
        guidedIndex: null,
        periodCards: [],
        autoplayTimer: null,
    };

    if (chartType === 'line' && annotations.length > 0) {
        payload.datasets = (payload.datasets || []).map((dataset) => ({ ...dataset }));
    }

    const chart = new Chart(context, {
        type: chartType,
        data: payload,
        options: (() => {
            const options = buildDefaultOptions(chartType);
            if (chartType === 'line') {
                options.plugins.cityAnnotationBands.annotations = annotations;
            }
            return options;
        })()
    });
    mountedCharts.push(chart);

    if (chartBlock) {
        annotationState.periodCards = Array.from(chartScope.querySelectorAll('[data-period-card]'));
        const resetButton = chartBlock.querySelector('[data-chart-reset]');
        if (resetButton) {
            resetButton.addEventListener('click', () => {
                clearAllFocus(chart, chartBlock, chartScope, annotations, annotationState);
            });
        }

        const exportButton = chartBlock.querySelector('[data-chart-export]');
        if (exportButton) {
            exportButton.addEventListener('click', () => {
                downloadChart(chart, filename);
            });
        }

        chartScope.querySelectorAll('[data-annotation-card], [data-annotation-year-target], [data-annotation-list-item], [data-annotation-open]').forEach((trigger) => {
            trigger.addEventListener('click', () => {
                const annotationId = trigger.dataset.annotationId;
                const targetYear = trigger.dataset.annotationYearTarget || trigger.dataset.annotationYear;
                const annotation = annotationId
                    ? annotations.find((item) => item.id === annotationId)
                    : annotations.find((item) => String(item.year) === String(targetYear));
                if (!annotation) {
                    return;
                }
                if (annotationId && !trigger.dataset.annotationYearTarget) {
                    jumpToPeriodForAnnotation(chartScope, annotation.year);
                    setChartFocusIndicator(chartScope, 'Vue complète active');
                    return;
                }
                if (trigger.dataset.annotationOpen !== undefined) {
                    jumpToPeriodForAnnotation(chartScope, annotation.year);
                    setChartFocusIndicator(chartScope, 'Vue complète active');
                    return;
                }
                if (trigger.dataset.periodId) {
                    annotationState.selectedPeriodId = trigger.dataset.periodId;
                } else {
                    annotationState.selectedPeriodId = null;
                    annotationState.guidedIndex = null;
                }
                annotationState.visibleIds.add(annotation.id);
                setActiveAnnotation(chart, chartBlock, chartScope, annotations, annotationState, annotation);
                zoomToAnnotation(chart, annotation);
                triggerTimelineFocus(chart, chartScope, annotations, annotation, annotationState.selectedPeriodId);
                if (trigger.dataset.annotationYearTarget) {
                    document.getElementById('city-annotations')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            });
        });

        chartScope.querySelectorAll('[data-period-card]').forEach((card) => {
            card.addEventListener('click', (event) => {
                if (event.target.closest('[data-annotation-year-target]') || event.target.closest('[data-period-only-annotations]')) {
                    return;
                }
                if (annotationState.selectedPeriodId === card.dataset.periodId) {
                    clearAllFocus(chart, chartBlock, chartScope, annotations, annotationState);
                    return;
                }
                focusPeriodCard(chart, chartBlock, chartScope, annotations, annotationState, card);
            });
        });

        chartScope.querySelectorAll('[data-period-only-annotations]').forEach((button) => {
            button.addEventListener('click', (event) => {
                event.stopPropagation();
                const periodId = button.dataset.periodId;
                const periodCard = periodId ? chartScope.querySelector(`[data-period-card][data-period-id="${periodId}"]`) : null;
                if (!periodCard) {
                    return;
                }
                focusPeriodCard(chart, chartBlock, chartScope, annotations, annotationState, periodCard, { onlyLinked: true });
            });
        });

        const guidedStart = chartScope.querySelector('[data-guided-start]');
        const guidedPrev = chartScope.querySelector('[data-guided-prev]');
        const guidedNext = chartScope.querySelector('[data-guided-next]');
        const guidedStop = chartScope.querySelector('[data-guided-stop]');
        const guidedReset = chartScope.querySelector('[data-guided-reset]');
        const guidedAutoplay = chartScope.querySelector('[data-guided-autoplay]');

        if (guidedStart) {
            guidedStart.addEventListener('click', () => {
                if (!annotationState.periodCards.length) {
                    return;
                }
                annotationState.guidedIndex = 0;
                focusPeriodCard(chart, chartBlock, chartScope, annotations, annotationState, annotationState.periodCards[0], { onlyLinked: true });
            });
        }

        if (guidedPrev) {
            guidedPrev.addEventListener('click', () => {
                if (!annotationState.periodCards.length) {
                    return;
                }
                const current = annotationState.guidedIndex ?? 0;
                annotationState.guidedIndex = Math.max(0, current - 1);
                focusPeriodCard(chart, chartBlock, chartScope, annotations, annotationState, annotationState.periodCards[annotationState.guidedIndex], { onlyLinked: true });
            });
        }

        if (guidedNext) {
            guidedNext.addEventListener('click', () => {
                if (!annotationState.periodCards.length) {
                    return;
                }
                const current = annotationState.guidedIndex ?? -1;
                annotationState.guidedIndex = Math.min(annotationState.periodCards.length - 1, current + 1);
                focusPeriodCard(chart, chartBlock, chartScope, annotations, annotationState, annotationState.periodCards[annotationState.guidedIndex], { onlyLinked: true });
            });
        }

        if (guidedStop) {
            guidedStop.addEventListener('click', () => {
                clearAllFocus(chart, chartBlock, chartScope, annotations, annotationState);
            });
        }

        if (guidedReset) {
            guidedReset.addEventListener('click', () => {
                clearAllFocus(chart, chartBlock, chartScope, annotations, annotationState);
            });
        }

        if (guidedAutoplay) {
            guidedAutoplay.addEventListener('click', () => {
                if (!annotationState.periodCards.length) {
                    return;
                }
                if (annotationState.autoplayTimer) {
                    window.clearInterval(annotationState.autoplayTimer);
                    annotationState.autoplayTimer = null;
                    syncGuidedReaderStatus(chartScope, annotations, annotationState);
                    return;
                }
                if (annotationState.guidedIndex === null || annotationState.guidedIndex === undefined) {
                    annotationState.guidedIndex = 0;
                    focusPeriodCard(chart, chartBlock, chartScope, annotations, annotationState, annotationState.periodCards[0], { onlyLinked: true });
                }
                annotationState.autoplayTimer = window.setInterval(() => {
                    const current = annotationState.guidedIndex ?? 0;
                    if (current >= annotationState.periodCards.length - 1) {
                        window.clearInterval(annotationState.autoplayTimer);
                        annotationState.autoplayTimer = null;
                        syncGuidedReaderStatus(chartScope, annotations, annotationState);
                        return;
                    }
                    annotationState.guidedIndex = current + 1;
                    focusPeriodCard(chart, chartBlock, chartScope, annotations, annotationState, annotationState.periodCards[annotationState.guidedIndex], { onlyLinked: true });
                }, 3600);
                syncGuidedReaderStatus(chartScope, annotations, annotationState);
            });
        }

        chartScope.querySelectorAll('[data-annotation-toggle]').forEach((toggle) => {
            toggle.addEventListener('click', (event) => {
                event.stopPropagation();
            });
            toggle.addEventListener('change', () => {
                const annotationId = toggle.dataset.annotationId;
                if (!annotationId) {
                    return;
                }
                if (toggle.checked) {
                    annotationState.visibleIds.add(annotationId);
                } else {
                    annotationState.visibleIds.delete(annotationId);
                }
                applyAnnotationState(chart, chartBlock, chartScope, annotations, annotationState);
            });
        });

        chartScope.querySelectorAll('[data-annotation-open]').forEach((button) => {
            button.addEventListener('click', (event) => {
                event.stopPropagation();
            });
        });

        const selectAllButton = chartScope.querySelector('[data-annotation-select-all]');
        if (selectAllButton) {
            selectAllButton.addEventListener('click', () => {
                clearAllFocus(chart, chartBlock, chartScope, annotations, annotationState);
            });
        }

        const clearButton = chartScope.querySelector('[data-annotation-clear]');
        if (clearButton) {
            clearButton.addEventListener('click', () => {
                annotationState.visibleIds.clear();
                applyAnnotationState(chart, chartBlock, chartScope, annotations, annotationState);
            });
        }

        const focusYear = new URLSearchParams(window.location.search).get('focus_annotation');
        if (focusYear) {
            const focusedAnnotation = annotations.find((item) => String(item.year) === focusYear);
            if (focusedAnnotation) {
                annotationState.visibleIds.add(focusedAnnotation.id);
                const matchingPeriod = chartScope.querySelector(`[data-period-card][data-linked-years*="${focusedAnnotation.year}"]`);
                annotationState.selectedPeriodId = matchingPeriod?.dataset.periodId || null;
                setActiveAnnotation(chart, chartBlock, chartScope, annotations, annotationState, focusedAnnotation);
                zoomToAnnotation(chart, focusedAnnotation);
                setChartFocusIndicator(chartScope, `Focus timeline: ${focusedAnnotation.label}`);
            }
        } else {
            applyAnnotationState(chart, chartBlock, chartScope, annotations, annotationState);
            setChartFocusIndicator(chartScope, 'Vue complète active');
            syncGuidedReaderStatus(chartScope, annotations, annotationState);
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    if (window.Chart && window.ChartZoom && !Chart.registry.plugins.get('zoom')) {
        Chart.register(window.ChartZoom);
    }
    if (window.Chart && !Chart.registry.plugins.get('cityAnnotationBands')) {
        Chart.register(cityAnnotationPlugin);
    }
    document.querySelectorAll('[data-chart]').forEach(mountChart);

    document.addEventListener('projetcity:themechange', () => {
        mountedCharts.forEach((chart) => applyThemeToChart(chart));
    });

    const backToTopButton = document.querySelector('[data-back-to-top]');
    if (backToTopButton) {
        const floatingDock = backToTopButton.closest('.floating-action-dock');
        const syncBackToTop = () => {
            const isVisible = window.scrollY > 420;
            backToTopButton.classList.toggle('is-visible', isVisible);
            if (floatingDock) {
                const keepDockVisible = floatingDock.classList.contains('is-persistent');
                floatingDock.classList.toggle('is-visible', keepDockVisible || isVisible);
            }
        };
        syncBackToTop();
        window.addEventListener('scroll', syncBackToTop, { passive: true });
        backToTopButton.addEventListener('click', () => {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
    }
});