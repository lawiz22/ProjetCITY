# -*- coding: utf-8 -*-
# ================================================================
# regionstats_RAW.py — Export automatique depuis la BD Central City Scrutinizer
# Ce fichier est régénéré à chaque import de région.
# NE PAS MODIFIER MANUELLEMENT — les changements seront écrasés.
# ================================================================
#
# Nombre de régions : 29
#

# ============================================================
# Alberta (Canada)
# ============================================================
REGION_NAME = "Alberta"
REGION_COUNTRY = "Canada"
REGION_COLOR = '#FFB300'

years = [1901, 1911, 1921, 1931, 1941, 1951, 1961, 1971, 1981, 1991, 2001, 2011, 2021]
population = [
    73022, 376993, 588454, 731605, 855502, 939501, 1232000, 1932000, 2696000, 2696000, 
    3290350, 3645257, 4262635
]

annotations = [
    (1981, 2696000, "📉 Récession économique — ralentissement (1981)", 'gray'),
]

# ============================================================
# Colombie-Britannique (Canada)
# ============================================================
REGION_NAME = "Colombie-Britannique"
REGION_COUNTRY = "Canada"
REGION_COLOR = '#1E3A5F'

years = [
    1871, 1881, 1891, 1901, 1911, 1921, 1931, 1941, 1951, 1961, 1971, 1981, 1991, 2001, 
    2011, 2021, 2024
]
population = [
    36247, 49459, 98173, 178657, 392480, 524582, 694263, 817861, 1165210, 1629082, 
    2184621, 2744467, 3282061, 3907738, 4400057, 5000879, 5500000
]

annotations = [
    (1871, 36247, "🏔️ Entrée dans la Confédération — la C.-B. rejoint le Canada (1871)", 'brown'),
    (1891, 98173, "🚂 Chemin de fer Canadien Pacifique — afflux de colons et travailleurs (1885)", 'orange'),
    (1911, 392480, "⛏️ Ruée vers l'or et boom forestier — explosion démographique (1898-1910)", 'gold'),
    (1941, 817861, "⚓ Seconde Guerre mondiale — industrie navale et militaire à Vancouver (1939-1945)", 'navy'),
    (1951, 1165210, "🏗️ Boom d'après-guerre — industrialisation et immigration massive (1946-1951)", 'blue'),
    (1971, 2184621, "🌲 Essor de l'industrie forestière — croissance soutenue et urbanisation (1960-1970)", 'green'),
    (1991, 3282061, "🌏 Immigration asiatique — vague majeure en provenance de Hong Kong (1986-1996)", 'red'),
    (2011, 4400057, "🏠 Boom immobilier de Vancouver — attractivité internationale (2000-2010)", 'purple'),
    (2021, 5000879, "📊 Recensement 2021 — cap des 5 millions franchi (2021)", 'teal'),
    (2024, 5500000, "🚀 Croissance record — immigration et attractivité technologique (2024)", 'darkred'),
]

# ============================================================
# Île-du-Prince-Édouard (Canada)
# ============================================================
REGION_NAME = "Île-du-Prince-Édouard"
REGION_COUNTRY = "Canada"
REGION_COLOR = '#008080'

years = [1901, 1911, 1921, 1931, 1941, 1951, 1961, 1971, 1981, 1991, 2001, 2011, 2021]
population = [
    88471, 91269, 87996, 83151, 80747, 75218, 72094, 72909, 72261, 64231, 135851, 140204, 
    164318
]

annotations = [
    (1901, 88471, "🌾 Agriculture dominante — population rurale majoritaire (1901)", 'brown'),
    (1921, 87996, "⚓ Déclin économique — baisse démographique liée à l'exode rural (1921)", 'orange'),
    (1941, 80747, "⚔️ Impact de la Seconde Guerre mondiale — stagnation démographique (1941)", 'red'),
    (1951, 75218, "🏭 Début de l'industrialisation — migration vers les villes (1951)", 'blue'),
    (1961, 72094, "🚜 Modernisation agricole — mécanisation réduisant les emplois (1961)", 'green'),
    (1971, 72909, "📉 Stabilisation démographique — fin de la baisse continue (1971)", 'purple'),
    (1991, 64231, "📉 Baisse démographique marquée — exode vers le continent (1991)", 'darkred'),
    (2001, 135851, "📈 Croissance démographique importante — recensement ajusté (2001)", 'gold'),
    (2011, 140204, "🏖️ Développement touristique — attractivité accrue (2011)", 'teal'),
    (2021, 164318, "🏡 Croissance continue — immigration et natalité en hausse (2021)", 'navy'),
]

# ============================================================
# Manitoba (Canada)
# ============================================================
REGION_NAME = "Manitoba"
REGION_COUNTRY = "Canada"
REGION_COLOR = '#4B9CD3'

years = [
    1870, 1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950, 1960, 1970, 1980, 1990, 2000, 
    2010, 2020
]
population = [
    25000, 70000, 130000, 280000, 450000, 570000, 670000, 730000, 840000, 980000, 
    1100000, 1150000, 1200000, 1210000, 1270000, 1375000
]

annotations = [
    (1870, 25000, "🛖 Fondation officielle du Manitoba — entrée dans la Confédération canadienne (1870)", 'brown'),
    (1880, 70000, "🚂 Expansion du chemin de fer — immigration massive (1880)", 'green'),
    (1900, 280000, "🏙️ Croissance urbaine rapide — Winnipeg devient un centre majeur (1900)", 'blue'),
    (1910, 450000, "🌾 Boom agricole — développement des Prairies (1910)", 'gold'),
    (1930, 670000, "📉 Grande Dépression — ralentissement démographique (1930)", 'darkred'),
    (1940, 730000, "⚔️ Efforts de guerre et industrialisation — Seconde Guerre mondiale (1940)", 'navy'),
    (1950, 840000, "🏭 Reconstruction et croissance économique d'après-guerre (1950)", 'orange'),
    (1960, 980000, "🚜 Modernisation agricole — mécanisation accrue (1960)", 'teal'),
    (1980, 1150000, "🏥 Amélioration des services sociaux — hausse de la qualité de vie (1980)", 'purple'),
    (2020, 1375000, "🌍 Diversification culturelle et économique — Manitoba contemporain (2020)", 'red'),
]

# ============================================================
# Newfoundland and Labrador (Canada)
# ============================================================
REGION_NAME = "Newfoundland and Labrador"
REGION_COUNTRY = "Canada"
REGION_COLOR = '#0055a4'

years = [1901, 1911, 1921, 1931, 1941, 1951, 1961, 1971, 1981, 1991, 2001, 2011, 2021]
population = [
    252047, 282594, 290000, 313000, 320000, 320000, 320000, 330000, 520000, 540000, 
    510000, 514536, 521758
]

annotations = [
    (1901, 252047, "📊 Recensement initial — population sous dominion britannique (1901)", 'brown'),
    (1931, 313000, "⚓ Croissance liée à la pêche — importance économique (1931)", 'blue'),
    (1971, 330000, "🚢 Expansion des infrastructures portuaires (1971)", 'navy'),
    (1981, 520000, "💥 Boom démographique — migration interne (1981)", 'red'),
    (1991, 540000, "⚠️ Déclin pêche traditionnelle — impact socio-économique (1991)", 'darkred'),
    (2001, 510000, "📉 Réduction population — exode rural (2001)", 'gray'),
    (2011, 514536, "🏞️ Développement tourisme — diversification économique (2011)", 'teal'),
    (2021, 521758, "🌐 Stabilisation démographique — nouvelles opportunités (2021)", 'purple'),
]

# ============================================================
# Nouveau-Brunswick (Canada)
# ============================================================
REGION_NAME = "Nouveau-Brunswick"
REGION_COUNTRY = "Canada"
REGION_COLOR = '#006633'

years = [1901, 1911, 1921, 1931, 1941, 1951, 1961, 1971, 1981, 1991, 2001, 2011, 2021]
population = [
    318854, 346459, 362258, 381315, 395857, 424573, 468284, 534475, 635094, 713573, 
    729498, 751171, 775610
]

annotations = [
    (1901, 318854, "📊 Premier recensement officiel complet — début des données modernes (1901)", 'brown'),
    (1921, 362258, "🌾 Croissance agricole — expansion rurale (1921)", 'green'),
    (1941, 395857, "⚔️ Impact de la Seconde Guerre mondiale — mobilisation et changements (1941)", 'red'),
    (1951, 424573, "🏭 Industrialisation — début de l'urbanisation (1951)", 'blue'),
    (1961, 468284, "🚜 Modernisation agricole — mécanisation accrue (1961)", 'orange'),
    (1971, 534475, "🏙️ Urbanisation rapide — croissance des villes (1971)", 'purple'),
    (1981, 635094, "📈 Pic de croissance démographique — boom économique (1981)", 'gold'),
    (1991, 713573, "🔄 Stabilisation démographique — ralentissement de la croissance (1991)", 'teal'),
    (2001, 729498, "🌍 Diversification culturelle — immigration accrue (2001)", 'navy'),
    (2021, 775610, "📉 Légère reprise démographique — défis actuels (2021)", 'darkred'),
]

# ============================================================
# Nouvelle-Écosse (Canada)
# ============================================================
REGION_NAME = "Nouvelle-Écosse"
REGION_COUNTRY = "Canada"
REGION_COLOR = '#0055a4'

years = [1901, 1911, 1921, 1931, 1941, 1951, 1961, 1971, 1981, 1991, 2001, 2011, 2021]
population = [
    440000, 460000, 480000, 500000, 520000, 540000, 560000, 580000, 600000, 620000, 
    640000, 670000, 700000
]

annotations = [
    (1901, 440000, "📈 Croissance démographique stable — recensement initial moderne (1901)", 'blue'),
    (1911, 460000, "🚢 Immigration et développement portuaire — expansion économique (1911)", 'green'),
    (1921, 480000, "⚓ Impact de la Première Guerre mondiale — retour des soldats (1921)", 'brown'),
    (1941, 520000, "💣 Seconde Guerre mondiale — mobilisation et changements sociaux (1941)", 'red'),
    (1951, 540000, "🏭 Industrialisation accrue — boom économique d'après-guerre (1951)", 'orange'),
    (1961, 560000, "🚜 Modernisation rurale — mécanisation de l'agriculture (1961)", 'teal'),
    (1971, 580000, "🏙️ Urbanisation croissante — croissance des villes (1971)", 'purple'),
    (1981, 600000, "📉 Déclin démographique relatif — émigration vers d'autres provinces (1981)", 'gray'),
    (1991, 620000, "🌊 Diversification économique — tourisme et services (1991)", 'gold'),
    (2001, 640000, "📊 Stabilisation de la population — politiques d'immigration (2001)", 'navy'),
    (2011, 670000, "🌍 Accroissement par immigration internationale — multiculturalisme (2011)", 'darkred'),
    (2021, 700000, "🏡 Croissance modérée — développement durable et qualité de vie (2021)", 'black'),
]

# ============================================================
# Nunavut (Canada)
# ============================================================
REGION_NAME = "Nunavut"
REGION_COUNTRY = "Canada"
REGION_COLOR = '#66ccff'

years = [1901, 1921, 1951, 1971, 1981, 1991, 2001, 2011, 2021]
population = [1000, 1500, 2500, 5000, 8000, 15000, 28000, 31000, 39000]

annotations = [
    (1901, 1000, "🧊 Population inuit traditionnelle — recensement colonial initial (1901)", 'blue'),
    (1921, 1500, "❄️ Premiers contacts et missions — augmentation lente (1921)", 'gray'),
    (1951, 2500, "🏥 Introduction des services de santé — croissance démographique (1951)", 'green'),
    (1971, 5000, "🏠 Début des établissements permanents — sédentarisation (1971)", 'orange'),
    (1981, 8000, "📜 Début des revendications territoriales — montée politique (1981)", 'purple'),
    (1991, 15000, "🗳️ Création du Nunavut — autonomie accrue (1991)", 'gold'),
    (2001, 28000, "🏙️ Développement urbain à Iqaluit — croissance rapide (2001)", 'teal'),
    (2011, 31000, "🌍 Sensibilisation climatique — impact sur mode de vie (2011)", 'navy'),
    (2021, 39000, "📈 Croissance démographique soutenue — population actuelle (2021)", 'red'),
]

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
# Saskatchewan (Canada)
# ============================================================
REGION_NAME = "Saskatchewan"
REGION_COUNTRY = "Canada"
REGION_COLOR = '#2E8B57'

years = [
    1901, 1906, 1911, 1916, 1921, 1926, 1931, 1936, 1941, 1946, 1951, 1956, 1961, 1966, 
    1971, 1976, 1981, 1986, 1991, 1996, 2001, 2006, 2011, 2016, 2021, 2024
]
population = [
    91279, 257763, 492432, 647835, 757510, 820738, 921785, 931547, 895992, 832688, 
    831728, 880665, 925181, 955344, 926242, 921323, 968313, 1009613, 988928, 990237, 
    978933, 985386, 1033381, 1098352, 1132505, 1214684
]

annotations = [
    (1901, 91279, "🌾 Début de la colonisation — Terres offertes aux pionniers (1901)", 'brown'),
    (1911, 492432, "🚂 Boom ferroviaire — Afflux massif de colons européens (1911)", 'orange'),
    (1931, 921785, "📈 Pic pré-crise — Apogée de la colonisation agricole (1931)", 'green'),
    (1936, 931547, "🌪️ Grande Dépression et Dust Bowl — Sécheresses dévastatrices (1930s)", 'darkred'),
    (1946, 832688, "📉 Exode rural — Mécanisation agricole et départs vers l'Ouest (1946)", 'gray'),
    (1961, 925181, "🏛️ Ère Tommy Douglas — Premiers soins de santé universels au Canada (1962)", 'blue'),
    (1986, 1009613, "🎯 Cap du million — La province franchit le million d'habitants (1986)", 'purple'),
    (1996, 990237, "⛽ Crise agricole — Chute des prix des céréales et émigration (1990s)", 'red'),
    (2011, 1033381, "🛢️ Boom des ressources — Potasse et pétrole attirent de nouveaux résidents (2011)", 'teal'),
    (2024, 1214684, "🌍 Croissance record — Immigration internationale soutenue (2024)", 'gold'),
]

# ============================================================
# Territoires du Nord-Ouest (Canada)
# ============================================================
REGION_NAME = "Territoires du Nord-Ouest"
REGION_COUNTRY = "Canada"
REGION_COLOR = '#006400'

years = [1901, 1911, 1921, 1931, 1941, 1951, 1961, 1971, 1981, 1991, 2001, 2011, 2021]
population = [
    11874, 12757, 14000, 15000, 16000, 20000, 23000, 26000, 39000, 39000, 39000, 41000, 
    45000
]

annotations = [
    (1901, 11874, "🛶 Population autochtone majoritaire — recensement initial (1901)", 'brown'),
    (1951, 20000, "🏭 Début de l'exploitation minière — croissance démographique (1951)", 'orange'),
    (2011, 41000, "🏥 Amélioration des services de santé — espérance de vie en hausse (2011)", 'teal'),
    (2021, 45000, "🌱 Croissance durable et développement économique (2021)", 'navy'),
]

# ============================================================
# Yukon (Canada)
# ============================================================
REGION_NAME = "Yukon"
REGION_COUNTRY = "Canada"
REGION_COLOR = '#4B9CD3'

years = [1901, 1911, 1921, 1931, 1941, 1951, 1961, 1971, 1981, 1991, 2001, 2011, 2021]
population = [8946, 8025, 4943, 4127, 4322, 4764, 6461, 11297, 21781, 29458, 30066, 35587, 42176]

annotations = [
    (1901, 8946, "⛏️ Ruée vers l'or — pic initial de population (1901)", 'gold'),
    (1911, 8025, "📉 Déclin post-ruée — départ des mineurs (1911)", 'brown'),
    (1921, 4943, "🏞️ Stabilisation rurale — population réduite (1921)", 'green'),
    (1941, 4322, "⚔️ Seconde Guerre mondiale — faible croissance (1941)", 'navy'),
    (1951, 4764, "🚂 Chemin de fer construit — début de développement (1951)", 'orange'),
    (1961, 6461, "🏗️ Modernisation et infrastructures (1961)", 'blue'),
    (1971, 11297, "🛢️ Découverte de ressources pétrolières (1971)", 'purple'),
    (1981, 21781, "🌲 Expansion économique et démographique (1981)", 'teal'),
    (1991, 29458, "🏙️ Urbanisation accrue — Whitehorse grandit (1991)", 'red'),
    (2001, 30066, "🌐 Diversification économique (2001)", 'gray'),
    (2011, 35587, "📈 Croissance démographique soutenue (2011)", 'darkred'),
    (2021, 42176, "🌟 Population record — développement durable (2021)", 'black'),
]

# ============================================================
# Arizona (États-Unis)
# ============================================================
REGION_NAME = "Arizona"
REGION_COUNTRY = "États-Unis"
REGION_COLOR = '#D2691E'

years = [1900, 1910, 1920, 1930, 1940, 1950, 1960, 1970, 1980, 1990, 2000, 2010, 2020]
population = [
    122931, 204354, 334162, 435573, 499261, 749587, 1367212, 1865403, 2718215, 3665228, 
    5130632, 6392017, 7151502
]

annotations = [
    (1930, 435573, "🌵 Croissance liée à l'agriculture et au cuivre — boom économique (1930)", 'brown'),
    (1940, 499261, "⚙️ Développement industriel pendant la Seconde Guerre mondiale (1940)", 'blue'),
    (1950, 749587, "🏜️ Expansion urbaine autour de Phoenix — début de l'urbanisation (1950)", 'orange'),
    (1960, 1367212, "🚀 Croissance démographique rapide — boom du désert (1960)", 'red'),
    (1970, 1865403, "🏢 Développement des infrastructures et industries (1970)", 'purple'),
    (1980, 2718215, "🌞 Popularité croissante comme destination touristique (1980)", 'gold'),
    (1990, 3665228, "🏠 Expansion résidentielle massive — migration interne (1990)", 'teal'),
    (2000, 5130632, "📈 Croissance économique soutenue — diversification (2000)", 'navy'),
    (2020, 7151502, "🌄 Phoenix devient la 5e plus grande ville des USA (2020)", 'darkred'),
]

# ============================================================
# California (États-Unis)
# ============================================================
REGION_NAME = "California"
REGION_COUNTRY = "États-Unis"
REGION_COLOR = '#FF6F61'

years = [1900, 1910, 1920, 1930, 1940, 1950, 1960, 1970, 1980, 1990, 2000, 2010, 2020]
population = [
    1486900, 2379400, 3426800, 5679000, 6909000, 10586200, 15717200, 19953100, 23667900, 
    29760000, 33871600, 37253900, 39538223
]

annotations = [
    (1900, 1486900, "🌾 Croissance agricole — début du XXe siècle (1900)", 'green'),
    (1910, 2379400, "🚂 Expansion ferroviaire — boom démographique (1910)", 'blue'),
    (1930, 5679000, "🌵 Dust Bowl migration — afflux de migrants (1930)", 'brown'),
    (1940, 6909000, "🏭 Industrialisation accrue — Seconde Guerre mondiale (1940)", 'orange'),
    (1950, 10586200, "🏠 Baby Boom — forte croissance post-guerre (1950)", 'gold'),
    (1960, 15717200, "🚀 Développement technologique — Silicon Valley naissante (1960)", 'purple'),
    (1970, 19953100, "🌉 Urbanisation rapide — croissance des villes (1970)", 'navy'),
    (1980, 23667900, "🎬 Hollywood mondialement reconnu — attractivité culturelle (1980)", 'red'),
    (1990, 29760000, "🌎 Immigration importante — diversification démographique (1990)", 'teal'),
    (2020, 39538223, "🏙️ Mégalopole californienne — population record (2020)", 'black'),
]

# ============================================================
# Colorado (États-Unis)
# ============================================================
REGION_NAME = "Colorado"
REGION_COUNTRY = "États-Unis"
REGION_COLOR = '#008080'

years = [1900, 1910, 1920, 1930, 1940, 1950, 1960, 1970, 1980, 1990, 2000, 2010, 2020]
population = [
    539700, 799024, 939629, 1042321, 1233023, 1498895, 1967131, 2528481, 3039749, 
    3294394, 4301261, 5029196, 5773714
]

annotations = [
    (1900, 539700, "🏞️ Début de l'exploitation minière — boom économique (1900)", 'brown'),
    (1910, 799024, "🚂 Expansion ferroviaire — ouverture du marché (1910)", 'orange'),
    (1930, 1042321, "🌾 Grande Dépression — ralentissement démographique (1930)", 'red'),
    (1940, 1233023, "⚙️ Industrialisation accrue — croissance modérée (1940)", 'blue'),
    (1950, 1498895, "🏭 Boom d'après-guerre — urbanisation rapide (1950)", 'green'),
    (1960, 1967131, "🏙️ Croissance des villes — Denver en expansion (1960)", 'purple'),
    (1970, 2528481, "🌄 Développement touristique — attractivité régionale (1970)", 'gold'),
    (1980, 3039749, "⛽ Boom énergétique — impact économique (1980)", 'teal'),
    (1990, 3294394, "📈 Croissance continue — diversification économique (1990)", 'navy'),
    (2020, 5773714, "🏡 Forte croissance résidentielle — attractivité durable (2020)", 'darkred'),
]

# ============================================================
# Florida (États-Unis)
# ============================================================
REGION_NAME = "Florida"
REGION_COUNTRY = "États-Unis"
REGION_COLOR = '#FFA500'

years = [1900, 1910, 1920, 1930, 1940, 1950, 1960, 1970, 1980, 1990, 2000, 2010, 2020]
population = [
    528542, 752619, 968470, 1439687, 1725281, 2776169, 4295735, 6302559, 9746324, 
    12937926, 15982378, 18801310, 21538187
]

annotations = [
    (1900, 528542, "🌴 Début du développement agricole — croissance initiale (1900)", 'green'),
    (1920, 968470, "🚂 Expansion ferroviaire — accès accru à la Floride (1920)", 'blue'),
    (1940, 1725281, "🏖️ Essor du tourisme — développement économique (1940)", 'orange'),
    (1950, 2776169, "✈️ Début du tourisme aérien — croissance rapide (1950)", 'purple'),
    (1960, 4295735, "🏙️ Urbanisation accélérée — boom démographique (1960)", 'red'),
    (1970, 6302559, "🛣️ Construction des autoroutes — mobilité accrue (1970)", 'teal'),
    (1990, 12937926, "🏡 Boom immobilier — forte immigration interne (1990)", 'brown'),
    (2000, 15982378, "🌞 Population senior en hausse — attractivité climatique (2000)", 'navy'),
    (2020, 21538187, "📈 Croissance continue — 3e État le plus peuplé (2020)", 'gold'),
]

# ============================================================
# Georgia (États-Unis)
# ============================================================
REGION_NAME = "Georgia"
REGION_COUNTRY = "États-Unis"
REGION_COLOR = '#3B7A57'

years = [1900, 1910, 1920, 1930, 1940, 1950, 1960, 1970, 1980, 1990, 2000, 2010, 2020]
population = [
    2068650, 2539230, 2728020, 2938320, 3444570, 3685230, 4169120, 4949870, 5446110, 
    6478210, 8186453, 9687653, 10711908
]

annotations = [
    (1900, 2068650, "📈 Croissance industrielle — début du boom urbain (1900)", 'brown'),
    (1910, 2539230, "🚂 Expansion ferroviaire — développement économique (1910)", 'orange'),
    (1930, 2938320, "🌾 Grande Dépression — ralentissement démographique (1930)", 'darkred'),
    (1940, 3444570, "⚙️ Seconde Guerre mondiale — industrialisation accrue (1940)", 'blue'),
    (1950, 3685230, "🏙️ Urbanisation rapide — croissance des villes (1950)", 'green'),
    (1970, 4949870, "🚀 Boom économique — migration vers Atlanta (1970)", 'gold'),
    (1990, 6478210, "✈️ Croissance démographique forte — attractivité régionale (1990)", 'teal'),
    (2000, 8186453, "🏢 Expansion métropolitaine — Atlanta en plein essor (2000)", 'purple'),
    (2010, 9687653, "🌎 Diversification culturelle — immigration accrue (2010)", 'navy'),
    (2020, 10711908, "📊 Croissance continue — 10 millions d'habitants (2020)", 'black'),
]

# ============================================================
# Illinois (États-Unis)
# ============================================================
REGION_NAME = "Illinois"
REGION_COUNTRY = "États-Unis"
REGION_COLOR = '#004B87'

years = [1900, 1910, 1920, 1930, 1940, 1950, 1960, 1970, 1980, 1990, 2000, 2010, 2020]
population = [
    4291873, 4844863, 6482503, 7454753, 7453294, 8776100, 10119293, 11023563, 11430602, 
    11430602, 12419293, 12830632, 12671821
]

annotations = [
    (1900, 4291873, "🚂 Industrialisation rapide — boom industriel et urbain (1900)", 'brown'),
    (1920, 6482503, "🏙️ Chicago devient un centre majeur — croissance urbaine (1920)", 'blue'),
    (1930, 7454753, "📉 Grande Dépression — ralentissement démographique (1930)", 'gray'),
    (1950, 8776100, "🏭 Après-guerre — boom économique et démographique (1950)", 'green'),
    (1960, 10119293, "🚗 Expansion des banlieues — exode urbain (1960)", 'orange'),
    (1970, 11023563, "🏢 Croissance industrielle continue — pic démographique (1970)", 'navy'),
    (1980, 11430602, "⚙️ Récession économique — stagnation démographique (1980)", 'red'),
    (1990, 11430602, "🏙️ Renaissance urbaine à Chicago — début de la diversification (1990)", 'purple'),
    (2000, 12419293, "🌎 Immigration accrue — diversification ethnique (2000)", 'teal'),
    (2020, 12671821, "🦠 Pandémie COVID-19 — impact démographique (2020)", 'darkred'),
]

# ============================================================
# Massachusetts (États-Unis)
# ============================================================
REGION_NAME = "Massachusetts"
REGION_COUNTRY = "États-Unis"
REGION_COLOR = '#1F77B4'

years = [1900, 1910, 1920, 1930, 1940, 1950, 1960, 1970, 1980, 1990, 2000, 2010, 2020]
population = [
    2996555, 3420696, 3515409, 3687929, 3780149, 4120094, 4999676, 5114562, 5529946, 
    6060986, 6349097, 6547629, 7029917
]

annotations = [
    (1900, 2996555, "🏭 Industrialisation majeure — croissance rapide (1900)", 'brown'),
    (1920, 3515409, "🦠 Pandémie de grippe espagnole — impact sanitaire (1918)", 'red'),
    (1940, 3780149, "⚙️ Seconde Guerre mondiale — mobilisation industrielle (1940)", 'navy'),
    (1950, 4120094, "🏙️ Baby-boom et urbanisation — forte croissance (1950)", 'orange'),
    (1960, 4999676, "🚀 Début de la révolution technologique — Boston comme hub (1960)", 'green'),
    (1970, 5114562, "🏢 Déclin industriel — stagnation démographique (1970)", 'gray'),
    (1980, 5529946, "🎓 Expansion des universités — attractivité accrue (1980)", 'blue'),
    (1990, 6060986, "🌎 Immigration accrue — diversification culturelle (1990)", 'purple'),
    (2000, 6349097, "💼 Croissance économique post-récession — reprise (2000)", 'teal'),
    (2020, 7029917, "🏠 Hausse des prix immobiliers — pression démographique (2020)", 'darkred'),
]

# ============================================================
# Nevada (États-Unis)
# ============================================================
REGION_NAME = "Nevada"
REGION_COUNTRY = "États-Unis"
REGION_COLOR = '#B0C4DE'

years = [1900, 1910, 1920, 1930, 1940, 1950, 1960, 1970, 1980, 1990, 2000, 2010, 2020]
population = [
    81255, 81535, 81235, 160083, 160083, 160083, 285278, 488738, 800493, 1201008, 
    1998257, 2700551, 3104614
]

annotations = [
    (1900, 81255, "🏜️ Population faible — début du XXe siècle (1900)", 'brown'),
    (1930, 160083, "⛏️ Boom minier — croissance démographique (1930)", 'orange'),
    (1950, 160083, "🎰 Début du jeu légal à Las Vegas — stagnation (1950)", 'green'),
    (1960, 285278, "🏢 Expansion urbaine — croissance rapide (1960)", 'blue'),
    (1970, 488738, "🎲 Las Vegas devient une destination majeure (1970)", 'red'),
    (1980, 800493, "🏨 Boom touristique — forte augmentation (1980)", 'purple'),
    (1990, 1201008, "🌆 Urbanisation continue — dépasse 1 million (1990)", 'gray'),
    (2000, 1998257, "🚀 Croissance économique rapide (2000)", 'gold'),
    (2010, 2700551, "🏙️ Expansion métropolitaine (2010)", 'teal'),
    (2020, 3104614, "📈 Population dépasse 3 millions (2020)", 'navy'),
]

# ============================================================
# New Jersey (États-Unis)
# ============================================================
REGION_NAME = "New Jersey"
REGION_COUNTRY = "États-Unis"
REGION_COLOR = '#003366'

years = [1900, 1910, 1920, 1930, 1940, 1950, 1960, 1970, 1980, 1990, 2000, 2010, 2020]
population = [
    2193736, 2617125, 3043985, 4115886, 4232033, 4724145, 7167939, 7577134, 7767339, 
    7732713, 8414350, 8791894, 9288994
]

annotations = [
    (1900, 2193736, "🏭 Industrialisation majeure — croissance rapide (1900)", 'brown'),
    (1910, 2617125, "🚂 Expansion ferroviaire — attractivité économique (1910)", 'orange'),
    (1930, 4115886, "🏙️ Urbanisation intense — New York proche (1930)", 'green'),
    (1940, 4232033, "⚔️ Seconde Guerre mondiale — impact démographique (1940)", 'blue'),
    (1950, 4724145, "🏠 Boom des banlieues — baby-boom (1950)", 'red'),
    (1960, 7167939, "🚗 Croissance automobile — étalement urbain (1960)", 'purple'),
    (1970, 7577134, "🏢 Développement industriel et tertiaire (1970)", 'gray'),
    (1990, 7732713, "🌎 Diversification ethnique — immigration accrue (1990)", 'gold'),
    (2000, 8414350, "💼 Économie de services — croissance stable (2000)", 'teal'),
    (2020, 9288994, "🏙️ Métropolisation et densification (2020)", 'navy'),
]

# ============================================================
# New York (États-Unis)
# ============================================================
REGION_NAME = "New York"
REGION_COUNTRY = "États-Unis"
REGION_COLOR = '#0033A0'

years = [1900, 1910, 1920, 1930, 1940, 1950, 1960, 1970, 1980, 1990, 2000, 2010, 2020]
population = [
    7268054, 9140400, 10367200, 12558000, 13216400, 14830100, 16069000, 18067000, 
    17558000, 17990400, 18976457, 19378102, 20201249
]

annotations = [
    (1900, 7268054, "🏙️ Croissance urbaine rapide — industrialisation et immigration massive (1900)", 'blue'),
    (1910, 9140400, "🚢 Vague d'immigration européenne — pic d'arrivées à Ellis Island (1910)", 'green'),
    (1930, 12558000, "🏭 Apogée industrielle — New York, capitale économique (1930)", 'orange'),
    (1940, 13216400, "⚔️ Impact de la Grande Dépression et début de la Seconde Guerre mondiale (1940)", 'darkred'),
    (1950, 14830100, "🚗 Expansion des banlieues — baby-boom d'après-guerre (1950)", 'gold'),
    (1970, 18067000, "🏚️ Déclin urbain et crise économique — exode vers la banlieue (1970)", 'brown'),
    (1980, 17558000, "🌆 Renaissance urbaine — début de la gentrification (1980)", 'teal'),
    (1990, 17990400, "🗽 Diversification culturelle accrue — immigration latino-américaine (1990)", 'purple'),
    (2000, 18976457, "📈 Croissance économique post-Guerre froide — boom technologique (2000)", 'navy'),
    (2020, 20201249, "🦠 Pandémie de COVID-19 — impact démographique et social (2020)", 'red'),
]

# ============================================================
# Ohio (États-Unis)
# ============================================================
REGION_NAME = "Ohio"
REGION_COUNTRY = "États-Unis"
REGION_COLOR = '#005bbb'

years = [1900, 1910, 1920, 1930, 1940, 1950, 1960, 1970, 1980, 1990, 2000, 2010, 2020]
population = [
    4129022, 4580584, 5039983, 5726731, 5905625, 7406129, 9961780, 10654302, 11142443, 
    10847120, 11353140, 11536504, 11799448
]

annotations = [
    (1900, 4129022, "🏭 Industrialisation rapide — croissance démographique forte (1900)", 'brown'),
    (1920, 5039983, "🚂 Expansion ferroviaire — développement urbain (1920)", 'orange'),
    (1940, 5905625, "⚙️ Seconde Guerre mondiale — boom industriel (1940)", 'green'),
    (1950, 7406129, "🏙️ Baby boom — pic de croissance démographique (1950)", 'blue'),
    (1960, 9961780, "🚗 Expansion des banlieues — urbanisation (1960)", 'red'),
    (1970, 10654302, "🏭 Déclin industriel commence — stagnation (1970)", 'purple'),
    (1980, 11142443, "📉 Récession économique — légère baisse (1980)", 'gray'),
    (1990, 10847120, "🏢 Transition vers économie tertiaire (1990)", 'gold'),
    (2000, 11353140, "🌆 Renouveau urbain — stabilisation (2000)", 'teal'),
    (2020, 11799448, "📊 Croissance modérée — diversification économique (2020)", 'navy'),
]

# ============================================================
# Oregon (États-Unis)
# ============================================================
REGION_NAME = "Oregon"
REGION_COUNTRY = "États-Unis"
REGION_COLOR = '#6495ED'

years = [1900, 1910, 1920, 1930, 1940, 1950, 1960, 1970, 1980, 1990, 2000, 2010, 2020]
population = [
    413150, 672765, 783389, 953786, 1089672, 1462755, 1768687, 2090609, 2618944, 2842321, 
    3421399, 3831074, 4237256
]

annotations = [
    (1900, 413150, "🌳 Colonisation européenne — début de la colonisation (1859)", 'green'),
    (1940, 1089672, "💼 Seconde Guerre mondiale — essor économique (1940)", 'blue'),
    (1960, 1768687, "🚗 Croissance démographique — expansion de l'automobile (1960)", 'orange'),
    (1980, 2618944, "🏙️ Urbanisation — croissance de Portland (1980)", 'red'),
    (2000, 3421399, "💻 Boom Internet — essor technologique (2000)", 'purple'),
    (2020, 4237256, "🌟 Évolution démographique — augmentation continue (2020)", 'navy'),
]

# ============================================================
# Pennsylvania (États-Unis)
# ============================================================
REGION_NAME = "Pennsylvania"
REGION_COUNTRY = "États-Unis"
REGION_COLOR = '#003366'

years = [1900, 1910, 1920, 1930, 1940, 1950, 1960, 1970, 1980, 1990, 2000, 2010, 2020]
population = [
    7360000, 7850000, 8450000, 9490000, 9680000, 11100000, 11700000, 11770000, 11830000, 
    11880000, 12280000, 12700000, 13000000
]

annotations = [
    (1900, 7360000, "🏭 Industrialisation massive — croissance rapide (1900)", 'brown'),
    (1910, 7850000, "🚂 Expansion ferroviaire — migration accrue (1910)", 'orange'),
    (1920, 8450000, "🏙️ Urbanisation forte — Pittsburgh et Philadelphie (1920)", 'green'),
    (1930, 9490000, "📉 Grande Dépression — ralentissement démographique (1930)", 'blue'),
    (1950, 11100000, "🏭 Boom industriel d'après-guerre — pic démographique (1950)", 'red'),
    (1970, 11770000, "🏢 Déclin industriel — début de stagnation (1970)", 'purple'),
    (1980, 11830000, "⚙️ Restructuration économique — perte d'emplois (1980)", 'gray'),
    (2000, 12280000, "🏥 Diversification économique — légère reprise (2000)", 'gold'),
    (2010, 12700000, "🌆 Croissance urbaine — revitalisation des villes (2010)", 'teal'),
    (2020, 13000000, "📊 Stabilisation démographique — population stable (2020)", 'navy'),
]

# ============================================================
# Texas (États-Unis)
# ============================================================
REGION_NAME = "Texas"
REGION_COUNTRY = "États-Unis"
REGION_COLOR = '#BF5700'

years = [1900, 1910, 1920, 1930, 1940, 1950, 1960, 1970, 1980, 1990, 2000, 2010, 2020]
population = [
    3048717, 3922956, 4665261, 5824494, 6414824, 7711194, 9579677, 11196730, 14229191, 
    16986510, 20851820, 25145561, 29145505
]

annotations = [
    (1900, 3048717, "🌾 Croissance agricole — expansion des fermes (1900)", 'green'),
    (1910, 3922956, "🚂 Développement ferroviaire — boom économique (1910)", 'blue'),
    (1920, 4665261, "🛢️ Découverte du pétrole à Spindletop — essor industriel (1920)", 'black'),
    (1930, 5824494, "🌾 Grande Dépression — ralentissement démographique (1930)", 'brown'),
    (1940, 6414824, "⚙️ Mobilisation WWII — industrialisation accrue (1940)", 'navy'),
    (1950, 7711194, "🏙️ Urbanisation rapide — croissance des villes (1950)", 'orange'),
    (1960, 9579677, "🚀 Début de la conquête spatiale — NASA à Houston (1960)", 'purple'),
    (1980, 14229191, "🏭 Boom pétrolier — forte croissance économique (1980)", 'red'),
    (2000, 20851820, "🌆 Expansion métropolitaine — Dallas et Houston (2000)", 'teal'),
    (2020, 29145505, "🌎 Diversification économique et démographique (2020)", 'gold'),
]

# ============================================================
# Washington (États-Unis)
# ============================================================
REGION_NAME = "Washington"
REGION_COUNTRY = "États-Unis"
REGION_COLOR = '#4B9CD3'

years = [1900, 1910, 1920, 1930, 1940, 1950, 1960, 1970, 1980, 1990, 2000, 2010, 2020]
population = [
    518103, 1106709, 1380104, 1686873, 1781357, 2379170, 2830000, 3104000, 4062000, 
    4868000, 5894000, 6723000, 7697000
]

annotations = [
    (1900, 518103, "🏞️ Croissance initiale — début du XXe siècle avec l'essor du chemin de fer (1900)", 'brown'),
    (1910, 1106709, "🚂 Expansion ferroviaire — boom démographique lié au transport (1910)", 'orange'),
    (1930, 1686873, "🏭 Industrialisation — croissance urbaine avant la Grande Dépression (1930)", 'green'),
    (1940, 1781357, "⚓ Seconde Guerre mondiale — développement naval et militaire (1940)", 'blue'),
    (1950, 2379170, "🏙️ Boom d'après-guerre — urbanisation rapide (1950)", 'red'),
    (1960, 2830000, "✈️ Expansion aérospatiale — Boeing et industrie aéronautique (1960)", 'purple'),
    (1980, 4062000, "💼 Croissance économique — diversification industrielle (1980)", 'gray'),
    (1990, 4868000, "🌐 Début de l'ère technologique — Seattle en plein essor (1990)", 'gold'),
    (2000, 5894000, "🖥️ Boom technologique — Microsoft et Amazon en croissance (2000)", 'teal'),
    (2020, 7697000, "🌲 Croissance durable — développement urbain et environnement (2020)", 'navy'),
]

# ============================================================
# Bretagne (France)
# ============================================================
REGION_NAME = "Bretagne"
REGION_COUNTRY = "France"
REGION_COLOR = '#2E8B57'

years = [
    1851, 1861, 1872, 1881, 1891, 1901, 1911, 1921, 1931, 1946, 1954, 1962, 1968, 1975, 
    1982, 1990, 1999, 2010, 2021
]
population = [
    2930000, 2980000, 3020000, 3080000, 3110000, 3135000, 3150000, 3070000, 3060000, 
    3020000, 3005000, 3025000, 3055000, 3185000, 3295000, 3395000, 3495000, 3305000, 
    3420000
]

annotations = [
    (1851, 2930000, "📜 Premier grand recensement moderne — base statistique régionale (1851)", 'brown'),
    (1911, 3150000, "⚓ Apogée démographique d'avant-guerre — croissance encore soutenue (1911)", 'green'),
    (1931, 3060000, "🌾 Stabilisation rurale — avant la Seconde Guerre mondiale (1931)", 'orange'),
    (1946, 3020000, "🏚️ Sortie de guerre — population encore fragilisée (1946)", 'gray'),
    (1962, 3025000, "🚜 Début du rebond — modernisation agricole et exode ralenti (1962)", 'blue'),
    (1975, 3185000, "🏙️ Reprise nette — attractivité résidentielle et littorale (1975)", 'teal'),
    (1990, 3395000, "✈️ Croissance soutenue — migrations de retraite et emplois urbains (1990)", 'purple'),
    (2021, 3420000, "🌊 Dynamique contemporaine — littoral attractif et métropolisation (2021)", 'gold'),
]
