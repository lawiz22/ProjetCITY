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
            context.lineWidth = annotation.active ? 3 : 1;
            context.strokeRect(left, chartArea.top, width, chartArea.bottom - chartArea.top);
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

function buildDefaultOptions(chartType) {
    const base = {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: {
            legend: {
                labels: {
                    color: '#1b2430',
                    font: {
                        family: 'Space Grotesk'
                    }
                }
            }
        },
        scales: {
            x: {
                ticks: {
                    color: '#5b6574',
                    autoSkip: true,
                    maxTicksLimit: chartType === 'line' ? 12 : 10,
                    maxRotation: 0,
                    minRotation: 0
                },
                grid: { color: 'rgba(27, 36, 48, 0.08)' }
            },
            y: {
                ticks: {
                    color: '#5b6574',
                    maxTicksLimit: 8
                },
                grid: { color: 'rgba(27, 36, 48, 0.08)' }
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

function setAnnotationDetail(chartBlock, annotation) {
    const detail = chartBlock?.querySelector('[data-annotation-detail]');
    if (!detail) {
        return;
    }
    if (!annotation) {
        detail.innerHTML = '<strong>Lecture des annotations</strong><p>Clique sur une bande verticale du graphique ou sur une carte ci-dessous pour afficher le détail ici.</p>';
        return;
    }
    detail.innerHTML = `
        <div class="annotation-detail-head">
            <span class="annotation-dot annotation-dot-large" style="background:${annotation.color}"></span>
            <div>
                <strong>${annotation.year}</strong>
                <span>${annotation.type || 'event'}</span>
            </div>
        </div>
        <h3>${annotation.label}</h3>
        <p>Bande verticale active sur la courbe. La couleur correspond à l’annotation historique de cette année.</p>
    `;
}

function getVisibleAnnotations(annotations, state) {
    return annotations.filter((annotation) => state.visibleIds.has(annotation.id));
}

function syncAnnotationCards(chartScope, visibleIds, activeId) {
    chartScope.querySelectorAll('[data-annotation-card]').forEach((card) => {
        const annotationId = card.dataset.annotationId;
        const isVisible = visibleIds.has(annotationId);
        card.classList.toggle('is-hidden', !isVisible);
        card.classList.toggle('is-active', isVisible && annotationId === activeId);
    });
}

function syncAnnotationFilters(chartScope, visibleIds) {
    chartScope.querySelectorAll('[data-annotation-toggle]').forEach((toggle) => {
        const annotationId = toggle.dataset.annotationId;
        const isVisible = visibleIds.has(annotationId);
        toggle.checked = isVisible;
        const pill = chartScope.querySelector(`[data-annotation-filter-pill][data-annotation-id="${annotationId}"]`);
        if (pill) {
            pill.classList.toggle('is-active', isVisible);
        }
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
    setAnnotationDetail(chartBlock, activeAnnotation);
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
    chart.options.scales.x.min = annotation.year - 25;
    chart.options.scales.x.max = annotation.year + 25;
    chart.update();
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

    if (annotations.length > 0) {
        canvas.addEventListener('click', (event) => {
            const rect = canvas.getBoundingClientRect();
            const x = event.clientX - rect.left;
            const y = event.clientY - rect.top;
            const matched = (chart.$annotationBands || []).find((band) => x >= band.left && x <= band.right && y >= band.top && y <= band.bottom);
            if (matched) {
                setActiveAnnotation(chart, chartBlock, chartScope, annotations, annotationState, matched);
            }
        });
    }

    if (chartBlock) {
        const resetButton = chartBlock.querySelector('[data-chart-reset]');
        if (resetButton) {
            resetButton.addEventListener('click', () => {
                if (chart.options?.scales?.x) {
                    delete chart.options.scales.x.min;
                    delete chart.options.scales.x.max;
                }
                if (typeof chart.resetZoom === 'function') {
                    chart.resetZoom();
                } else {
                    chart.update();
                }
                setActiveAnnotation(chart, chartBlock, chartScope, annotations, annotationState, null);
            });
        }

        const exportButton = chartBlock.querySelector('[data-chart-export]');
        if (exportButton) {
            exportButton.addEventListener('click', () => {
                downloadChart(chart, filename);
            });
        }

        chartScope.querySelectorAll('[data-annotation-card]').forEach((card) => {
            card.addEventListener('click', () => {
                const annotationId = card.dataset.annotationId;
                const annotation = annotations.find((item) => item.id === annotationId);
                if (!annotation) {
                    return;
                }
                setActiveAnnotation(chart, chartBlock, chartScope, annotations, annotationState, annotation);
                zoomToAnnotation(chart, annotation);
            });
        });

        chartScope.querySelectorAll('[data-annotation-toggle]').forEach((toggle) => {
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

        const selectAllButton = chartScope.querySelector('[data-annotation-select-all]');
        if (selectAllButton) {
            selectAllButton.addEventListener('click', () => {
                annotations.forEach((annotation) => {
                    annotationState.visibleIds.add(annotation.id);
                });
                applyAnnotationState(chart, chartBlock, chartScope, annotations, annotationState);
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
                setActiveAnnotation(chart, chartBlock, chartScope, annotations, annotationState, focusedAnnotation);
                zoomToAnnotation(chart, focusedAnnotation);
            }
        } else {
            applyAnnotationState(chart, chartBlock, chartScope, annotations, annotationState);
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
});