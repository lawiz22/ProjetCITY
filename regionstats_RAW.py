# -*- coding: utf-8 -*-
# ================================================================
# regionstats_RAW.py — Export automatique depuis la BD Central City Scrutinizer
# Ce fichier est régénéré à chaque import de région.
# NE PAS MODIFIER MANUELLEMENT — les changements seront écrasés.
# ================================================================
#
# Nombre de régions : 3
#

# ============================================================
# Ontario (Canada)
# ============================================================
REGION_NAME = "Ontario"
REGION_COUNTRY = "Canada"
REGION_COLOR = '#0073CF'

years = [1901, 1911, 1921, 1931, 1941, 1951, 1961, 1971, 1981, 1991, 2001, 2011, 2021]
population = [
    2372820, 3047337, 3557436, 4170000, 4830000, 5820000, 7240000, 8600000, 10600000, 
    11400000, 11700000, 12800000, 14700000
]

annotations = [
    (1901, 2372820, "🌾 Croissance agricole — début du XXe siècle marqué par l'expansion rurale (1901)", 'green'),
    (1911, 3047337, "🏭 Industrialisation — essor industriel et urbanisation (1911)", 'blue'),
    (1931, 4170000, "📉 Grande Dépression — ralentissement économique et démographique (1931)", 'brown'),
    (1951, 5820000, "👶 Baby-boom — forte croissance démographique post-Seconde Guerre mondiale (1951)", 'orange'),
    (1971, 8600000, "🏙️ Urbanisation rapide — croissance des villes majeures comme Toronto (1971)", 'purple'),
    (1991, 11400000, "🌐 Immigration accrue — diversification culturelle et démographique (1991)", 'teal'),
    (2021, 14700000, "🏆 Ontario, province la plus peuplée du Canada (2021)", 'red'),
]

# ============================================================
# Québec (Canada)
# ============================================================
REGION_NAME = "Québec"
REGION_COUNTRY = "Canada"
REGION_COLOR = '#003366'

years = [1901, 1911, 1921, 1931, 1941, 1951, 1961, 1971, 1981, 1991, 2001, 2011, 2021]
population = [
    1910000, 2220000, 2470000, 2740000, 3030000, 3520000, 4250000, 5020000, 5700000, 
    6400000, 7000000, 8000000, 8500000
]

annotations = [
    (1901, 1910000, "📈 Croissance démographique — début du XXe siècle, population rurale majoritaire (1901)", 'green'),
    (1931, 2740000, "🏭 Industrialisation — urbanisation croissante dans les villes comme Montréal et Québec (1931)", 'blue'),
    (1941, 3030000, "⚔️ Seconde Guerre mondiale — impact modéré sur la démographie régionale (1941)", 'gray'),
    (1951, 3520000, "👶 Baby-boom — forte croissance démographique après-guerre (1951)", 'gold'),
    (1961, 4250000, "📚 Révolution tranquille — modernisation et urbanisation accélérée (1961)", 'purple'),
    (1971, 5020000, "🏙️ Urbanisation majeure — majorité de la population vit désormais en milieu urbain (1971)", 'navy'),
    (1991, 6400000, "🌍 Immigration accrue — diversification de la population (1991)", 'orange'),
    (2011, 8000000, "🏥 Vieillissement de la population — allongement de l'espérance de vie (2011)", 'brown'),
    (2021, 8500000, "🦠 Pandémie COVID-19 — impact sanitaire et démographique (2021)", 'red'),
]

# ============================================================
# California (États-Unis)
# ============================================================
REGION_NAME = "California"
REGION_COUNTRY = "États-Unis"
REGION_COLOR = '#FF6F61'

years = [1900, 1910, 1920, 1930, 1940, 1950, 1960, 1970, 1980, 1990, 2000, 2010, 2020]
population = [
    14873791, 23767981, 34268643, 42315490, 56772500, 10586200, 15717204, 19953134, 
    23667902, 29760021, 33871648, 37253956, 39538223
]

annotations = [
    (1900, 14873791, "🌾 Croissance agricole — boom de la production agricole (1900)", 'green'),
    (1910, 23767981, "🚂 Expansion ferroviaire — développement des infrastructures (1910)", 'blue'),
    (1920, 34268643, "🏙️ Urbanisation rapide — croissance des villes (1920)", 'orange'),
    (1940, 56772500, "⚙️ Industrialisation — essor industriel avant la guerre (1940)", 'purple'),
    (1950, 10586200, "🏠 Baby-boom — forte augmentation démographique post-guerre (1950)", 'gold'),
    (1960, 15717204, "🚗 Expansion automobile — développement des banlieues (1960)", 'brown'),
    (1980, 23667902, "🌉 Développement technologique — Silicon Valley en essor (1980)", 'teal'),
    (1990, 29760021, "🌎 Diversification culturelle — immigration accrue (1990)", 'navy'),
    (2010, 37253956, "🌞 Tourisme et économie verte — attractivité renforcée (2010)", 'red'),
    (2020, 39538223, "🏙️ Mégalopole californienne — population record (2020)", 'black'),
]
