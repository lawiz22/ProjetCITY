import matplotlib.pyplot as plt
import numpy as np

CITY_NAME = "Denver, Colorado"
CITY_COLOR = '#FF6B35'

years = [1860, 1870, 1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950,
         1960, 1970, 1980, 1990, 2000, 2010, 2020]
population = [4749, 4759, 35629, 106713, 133859, 213381, 256491, 287861,
              322412, 415786, 493887, 514678, 492365, 467610,
              554636, 600158, 715522]

annotations = [
    (1860, 4749,   "⛏️ Gold Rush — Cherry Creek 1858",   'gold',  (1861, 1500)),
    (1880, 35629,  "🚂 Railroad arrive — boom!",          'gray',  (1862, 20000)),
    (1890, 106713, "🥈 Silver boom & bust",               'silver',(1872, 80000)),
    (1910, 213381, "🌾 Hub agricole Great Plains",        'green', (1892, 280000)),
    (1940, 322412, "✈️ Lowry Air Force Base — WWII",     'navy',  (1922, 450000)),
    (1950, 415786, "☢️ Rocky Flats — Cold War boom",     'red',   (1932, 600000)),
    (1970, 514678, "🛢️ Oil shale boom 1970s",            'black', (1952, 700000)),
    (1980, 492365, "💥 Oil bust (1982) — krach",          'orange',(1964, 750000)),
    (2000, 554636, "💻 Tech & LoDo renaissance",          'teal',  (1982, 800000)),
    (2020, 715522, "🌿 Cannabis + outdoor boom",          'green', (2003, 850000)),
]



import matplotlib.pyplot as plt
import numpy as np

CITY_NAME = "Sacramento, California"
CITY_COLOR = '#FFD700'

years = [1850, 1860, 1870, 1880, 1890, 1900, 1910, 1920, 1930, 1940,
         1950, 1960, 1970, 1980, 1990, 2000, 2010, 2020]
population = [6820, 13785, 16283, 21420, 26386, 29282, 44696, 65908,
              93750, 105958, 137572, 191667, 257105, 275741,
              369365, 407018, 466488, 524943]

annotations = [
    (1850, 6820,   "⛏️ Gold Rush — porte d'entrée 1849",  'gold',  (1851, 2000)),
    (1860, 13785,  "🚂 Pony Express terminus 1860",        'brown', (1852, 8000)),
    (1870, 16283,  "🔨 Transcontinental Railroad (1869)", 'gray',  (1861, 25000)),
    (1900, 29282,  "🌾 Capitale agricole Californie",      'green', (1882, 45000)),
    (1940, 105958, "✈️ Mather & McClellan AF Bases",      'navy',  (1922, 180000)),
    (1950, 137572, "🏛️ Capitale État — boom fonctionnaires",'blue', (1932, 250000)),
    (1970, 257105, "🌉 Autoroutes & suburbanisation",      'gray',  (1952, 380000)),
    (2000, 407018, "🏠 Immobilier fuite SF/Bay Area",      'teal',  (1982, 480000)),
    (2010, 466488, "💥 Crise subprime — Sacramento #1 (2008)", 'red', (1990, 560000)),
    (2020, 524943, "🌿 Cannabis + tech spillover",         'green', (2005, 580000)),
]


import matplotlib.pyplot as plt
import numpy as np

CITY_NAME = "Atlanta, Georgia"
CITY_COLOR = '#B22222'

years = [1850, 1860, 1870, 1880, 1890, 1900, 1910, 1920, 1930, 1940,
         1950, 1960, 1970, 1980, 1990, 2000, 2010, 2020]
population = [2572, 9554, 21789, 37409, 65533, 89872, 154839, 200616,
              270366, 302288, 331314, 487455, 496973, 425022,
              394017, 416474, 420003, 498715]

annotations = [
    (1850, 2572,   "🚂 Terminus railroad — fondée 1837",  'gray',  (1851, 800)),
    (1860, 9554,   "🔥 Sherman brûle Atlanta — Civil War (1864)", 'red', (1852, 15000)),
    (1880, 37409,  "🔨 Reconstruction & New South",        'brown', (1862, 60000)),
    (1890, 65533,  "🎪 Cotton States Exposition (1895)",   'green', (1872, 110000)),
    (1920, 200616, "🥤 Coca-Cola empire naît ici",         'red',   (1902, 280000)),
    (1940, 302288, "✈️ Hub aviation Sud-Est USA",          'navy',  (1922, 420000)),
    (1960, 487455, "✊ MLK & Civil Rights Movement",       'black', (1942, 560000)),
    (1980, 425022, "📺 CNN fondée ici — Ted Turner",       'teal',  (1962, 580000)),
    (2000, 416474, "🏅 Jeux Olympiques Atlanta (1996)",    'gold',  (1978, 600000)),
    (2020, 498715, "🎬 Hollywood du Sud — film industry",  'purple',(2003, 650000)),
]

import matplotlib.pyplot as plt
import numpy as np

CITY_NAME = "Vancouver, British Columbia"
CITY_COLOR = '#2E8B57'

years = [1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950, 1960, 1970,
         1981, 1991, 2001, 2011, 2021]
population = [1000, 13709, 27010, 100401, 117217, 246593, 275353,
              344833, 384522, 426256, 414281, 471844, 545671,
              603502, 662248]

annotations = [
    (1890, 13709,  "🔥 Grand feu de Vancouver (1886)",          'red',    (1882, 30000)),
    (1910, 100401, "🚂 CPR terminus — boom préguerre (1887)",   'brown',  (1892, 160000)),
    (1940, 275353, "😢 Internement Japonais-Canadiens (1942)",  'black',  (1922, 380000)),
    (1970, 426256, "🌿 Greenpeace fondé à Vancouver (1971)",    'green',  (1952, 480000)),
    (1981, 414281, "🎪 Expo 86 — transformation urbaine (1986)",'purple', (1963, 520000)),
    (1991, 471844, "🏠 Capitaux Hong Kong — boom immo (1997)",  'gold',   (1973, 560000)),
    (2021, 662248, "💰 Ville la moins abordable Canada (2024)", 'red',    (2005, 620000)),
]


CITY_NAME = "Burnaby, British Columbia"
CITY_COLOR = '#1f77b4'

years = [1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950, 1960, 1970,
         1980, 1990, 2000, 2010, 2020]

population = [500, 2000, 4500, 9876, 12878, 24284, 30327, 58376,
              100157, 125660, 136494, 158858, 193954, 223218, 249125]

annotations = [
    (1890, 2000,   "🌲 Incorporation ville de Burnaby (1892)",       'green',  (1882, 8000)),
    (1920, 12878,  "🚃 Interurban tram — lien avec Vancouver (1913)",'brown',  (1902, 25000)),
    (1950, 58376,  "🏭 Boom industriel postguerre (1945)",           'gray',   (1932, 80000)),
    (1970, 125660, "🎓 SFU inauguration — Simon Fraser (1965)",      'red',    (1952, 150000)),
    (1990, 158858, "🎪 Metrotown — plus grand mall BC (1986)",       'purple', (1972, 190000)),
    (2010, 223218, "🎬 Hollywood North — studios Burnaby (2005)",    'gold',   (1992, 240000)),
    (2020, 249125, "🏗️ Densification massive — condos SkyTrain",    'orange', (2004, 260000)),
]

CITY_NAME = "New Westminster, British Columbia"
CITY_COLOR = '#8B0000'

years = [1860, 1870, 1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950,
         1960, 1970, 1980, 1990, 2000, 2010, 2020]

population = [500, 1500, 3000, 6678, 6499, 13199, 14495, 17524,
              21967, 28639, 33654, 42835, 38393, 43585, 54656, 65976, 78916]

annotations = [
    (1860, 500,   "👑 Capitale BC — fondée par Royal Engineers (1858)",   'red',    (1862, 8000)),
    (1880, 3000,  "🌲 Scieries — bois Pacifique — boom export (1875)",    'green',  (1872, 12000)),
    (1900, 6499,  "🔥 Grand incendie détruit ville (1898)",               'orange', (1882, 18000)),
    (1910, 13199, "🚂 CPR + tramways — croissance rapide (1905)",         'brown',  (1892, 24000)),
    (1940, 21967, "⚓ Industrie guerre — chantiers navals (1940)",        'gray',   (1922, 32000)),
    (1980, 38393, "📉 Désindustrialisation — perd population (1975)",     'red',    (1962, 42000)),
    (2000, 54656, "🚝 SkyTrain — renaissance urbaine (1990)",             'blue',   (1982, 60000)),
    (2020, 78916, "🏗️ Densification — condos SkyTrain (2015)",           'orange', (2002, 82000)),
]


CITY_NAME = "Victoria, British Columbia"
CITY_COLOR = '#1B4F72'

years = [1858, 1870, 1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950,
         1960, 1970, 1980, 1990, 2000, 2010, 2020]

population = [300, 3000, 5925, 16841, 20919, 26826, 38727, 39082,
              44068, 51331, 54941, 61761, 64379, 71228, 74125, 80017, 92141]

annotations = [
    (1858, 300,   "🏴󠁧󠁢󠁳󠁣󠁴󠁿 Fort Victoria — HBC — capitale colonie (1843)",    'red',    (1860, 12000)),
    (1870, 3000,  "🏛️ Capitale BC confirmée — New West perdante (1866)", 'brown',  (1874, 28000)),
    (1900, 20919, "⛏️ Ruée Klondike — transit massif (1898)",            'gold',   (1882, 38000)),
    (1910, 26826, "🏗️ Boom Edwardien — Empress Hotel (1908)",           'green',  (1892, 50000)),
    (1940, 44068, "⚓ WWII — base navale Esquimalt (1940)",              'gray',   (1922, 62000)),
    (1970, 61761, "🎓 UVic — université complète (1963)",               'blue',   (1952, 72000)),
    (2000, 74125, "🌸 Tourisme — 'Most livable' (1995)",                'pink',   (1982, 85000)),
    (2020, 92141, "🏗️ Densification — crise logement (2018)",          'orange', (2002, 96000)),
]

CITY_NAME = "Mississauga, Ontario"
CITY_COLOR = '#C8102E'

years = [1850, 1870, 1890, 1910, 1930, 1950, 1960, 1970, 1980, 1990,
         2000, 2010, 2020]

population = [3000, 4500, 6000, 8000, 12000, 35000, 65000, 156000,
              315000, 463388, 612925, 713443, 717961]

annotations = [
    (1850, 3000,   "🌿 Villages ruraux — Credit River — fermes (1850)",     'green',  (1852, 60000)),
    (1910, 8000,   "🍑 Agriculture — vergers, maraîchers (1900)",           'orange', (1912, 100000)),
    (1950, 35000,  "✈️ Aéroport Malton — Avro Arrow (1947)",               'blue',   (1942, 160000)),
    (1970, 156000, "🏗️ Suburbanisation explosive — 401 (1960)",            'brown',  (1962, 240000)),
    (1970, 156000, "🏛️ Ville de Mississauga créée (1974)",                 'red',    (1972, 340000)),
    (1980, 315000, "💼 Hazel McCallion — maire 36 ans (1978)",             'purple', (1978, 430000)),
    (1990, 463388, "🏢 Bureaux — Masonville, Erin Mills (1985)",           'gray',   (1988, 530000)),
    (2000, 612925, "🌏 Immigration massive — diversité (1995)",            'gold',   (1998, 650000)),
    (2020, 717961, "🚝 LRT Hurontario — enfin (2024)",                     'orange', (2018, 750000)),
]

CITY_NAME = "Richmond, British Columbia"
CITY_COLOR = '#B8860B'

years = [1860, 1870, 1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950,
         1960, 1970, 1980, 1990, 2000, 2010, 2020]

population = [200, 500, 1000, 2500, 4500, 7500, 10000, 13500, 16000, 22000,
              43000, 62121, 96154, 126624, 164345, 190473, 209937]

annotations = [
    (1880, 1000,   "🌾 Drainage & agriculture — îles Lulu/Sea (1879)",     'green',  (1862, 8000)),
    (1880, 1000,   "🐟 Conserveries saumon Fraser — boom (1870)",          'blue',   (1872, 15000)),
    (1930, 13500,  "✈️ Aéroport Sea Island ouvert — futur YVR (1931)",     'brown',  (1912, 22000)),
    (1940, 16000,  "⛩️ Internement Japonais-Canadiens (1942)",             'red',    (1922, 30000)),
    (1960, 43000,  "🌉 Ponts & banlieue — explosion suburbaine (1960)",    'orange', (1942, 50000)),
    (1970, 62121,  "🌾 Agricultural Land Reserve protège terres (1973)",   'green',  (1952, 70000)),
    (2000, 164345, "🏮 Immigration HK/Chine — ville sino-canadienne (1990)",'red',   (1982, 175000)),
    (2010, 190473, "🚝 Canada Line SkyTrain — City Centre (2009)",         'blue',   (1992, 200000)),
]


CITY_NAME = "Brampton, Ontario"
CITY_COLOR = '#8B0000'

years = [1860, 1870, 1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950,
         1960, 1970, 1980, 1990, 2000, 2010, 2020]

population = [1200, 2500, 4000, 5000, 5986, 6000, 6500, 8000, 10000,
              17000, 37000, 102000, 149000, 234000, 325000, 523911, 656480]

annotations = [
    (1860, 1200,   "🌸 Flower Town — serres florales dominantes (1860)",       'green',  (1862, 20000)),
    (1880, 4000,   "🚂 Grand Trunk Railway — connexion Toronto (1875)",         'brown',  (1872, 40000)),
    (1900, 5986,   "📚 Bibliothèque Carnegie construite (1907)",                'blue',   (1882, 60000)),
    (1930, 8000,   "🏛️ Ville de comté stable — identité floricole (1930)",     'gray',   (1912, 80000)),
    (1970, 102000, "🏙️ City of Brampton — fusion municipale (1974)",           'orange', (1952, 130000)),
    (1980, 149000, "🌸 Fin des serres — cheminée démolie (1977)",              'red',    (1962, 180000)),
    (2000, 325000, "🚗 Boom suburbain GTA — autoroutes 410/407 (1995)",        'purple', (1982, 350000)),
    (2020, 656480, "🌍 2e ville GTA — immigration massive (2020)",             'blue',   (2002, 700000)),
]

CITY_NAME = "Surrey, British Columbia"
CITY_COLOR = '#006400'

years = [1860, 1870, 1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950,
         1960, 1970, 1980, 1990, 2000, 2010, 2020]

population = [200, 500, 1000, 2000, 3000, 5000, 7000, 10000, 14000,
              22000, 70000, 120000, 147138, 245173, 347825, 468251, 568322]

annotations = [
    (1860, 200,    "🏞️ Territoire Semiahmoo/Kwantlen — ruée Fraser (1858)",   'brown',  (1862, 30000)),
    (1880, 1000,   "🌲 Incorporation municipalité — fermes/scieries (1879)",  'green',  (1872, 60000)),
    (1910, 5000,   "🚂 BC Electric Railway — désenclavement (1905)",          'brown',  (1892, 90000)),
    (1940, 14000,  "🌾 Surrey rural — agriculture dominante (1940)",          'olive',  (1922, 120000)),
    (1960, 70000,  "🚗 Boom suburbain — ville-dortoir Vancouver (1955)",      'orange', (1942, 150000)),
    (1990, 245173, "🏙️ Incorporation officielle City of Surrey (1993)",       'blue',   (1972, 280000)),
    (2000, 347825, "🚝 SkyTrain étendu — redéveloppement Whalley (1994)",     'purple', (1982, 390000)),
    (2020, 568322, "🌍 2e ville CB — immigration Asie du Sud (2020)",         'red',    (2002, 620000)),
]

CITY_NAME = "Boucherville, Québec"
CITY_COLOR = '#003153'

years = [1860, 1870, 1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950,
         1960, 1970, 1980, 1990, 2000, 2010, 2020]

population = [3200, 3500, 3800, 4000, 4200, 4500, 4800, 5200, 5800,
              7000, 11000, 19000, 29000, 33000, 38000, 41928, 45000]

annotations = [
    (1860, 3200,  "⛪ Paroisse Sainte-Famille 1668 — vieux bourg seigneurial",  'navy',   (1862, 8000)),
    (1870, 3500,  "🔥 Incendie 1843 — reconstruction en pierre du village",     'red',    (1872, 14000)),
    (1900, 4200,  "🌿 Briqueteries argile — économie artisanale (1900)",        'brown',  (1882, 18000)),
    (1940, 5800,  "✝️ Tissu social catholique — Collège fondé (1935)",          'gray',   (1922, 22000)),
    (1960, 11000, "🚗 Tunnel La Fontaine — suburbanisation (1967)",             'orange', (1942, 26000)),
    (1970, 19000, "🏘️ Explosion banlieue — bungalows massifs (1970)",          'purple', (1952, 32000)),
    (1980, 29000, "🏭 Parc industriel rive sud — pharma/manu (1975)",           'blue',   (1962, 38000)),
    (2010, 41928, "🏛️ Défusion 2006 — autonomie retrouvée (2006)",             'green',  (1992, 46000)),
]

CITY_NAME = "Ottawa, Ontario"
CITY_COLOR = '#CC0000'

years = [1860, 1870, 1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950,
         1960, 1970, 1980, 1990, 2000, 2010, 2020]

population = [14669, 21545, 27412, 44154, 59928, 87062, 107843, 126872,
              154951, 202045, 268206, 380000, 491000, 678000, 774072,
              883391, 1017449]

annotations = [
    (1860, 14669,  "🏗️ Canal Rideau — Bytown devient Ottawa (1855)",           'blue',   (1862, 80000)),
    (1870, 21545,  "👑 Capitale confédération — Parlement (1867)",              'red',    (1872, 140000)),
    (1900, 59928,  "🌲 Scieries Booth & Eddy — géants du bois (1900)",         'green',  (1882, 200000)),
    (1920, 107843, "🏛️ Plan Holt — urbanisme de capitale (1915)",              'brown',  (1902, 260000)),
    (1950, 202045, "🌿 Plan Gréber — ceinture verte/promenades (1950)",        'olive',  (1932, 330000)),
    (1970, 380000, "🗣️ Loi langues officielles — ville bilingue (1969)",       'purple', (1952, 430000)),
    (2000, 774072, "💻 Silicon Valley du Nord — crash Nortel (2001)",           'orange', (1982, 830000)),
    (2020, 1017449,"🚝 LRT inauguré — 1 million hab. (2019)",                  'blue',   (2002, 1080000)),
]

CITY_NAME = "Hamilton, Ontario"
CITY_COLOR = '#8B0000'

years = [1860, 1870, 1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950,
         1960, 1970, 1980, 1990, 2000, 2010, 2020]

population = [19096, 26716, 35961, 48959, 52634, 81969, 114151, 155547,
              166337, 208321, 273991, 309173, 306434, 318499, 490268,
              519949, 569353]

annotations = [
    (1860, 19096,  "🚂 Grand Trunk Railway — nœud ferroviaire (1856)",        'brown',  (1862, 60000)),
    (1880, 35961,  "🔩 Fonderies métal — 'The Ambitious City' (1880)",        'gray',   (1872, 110000)),
    (1910, 81969,  "🏭 Stelco 1910 + Dofasco 1912 — capitale acier",         'red',    (1892, 160000)),
    (1940, 166337, "⚔️ Acier militaire — production max guerres (1940)",      'navy',   (1922, 210000)),
    (1960, 273991, "💪 Apogée Steeltown — syndicats forts (1960)",            'orange', (1942, 270000)),
    (1980, 306434, "📉 Crise acier — concurrence Japon/Corée (1975)",         'red',    (1962, 340000)),
    (2000, 490268, "🏙️ Fusion municipale — ville élargie (2001)",            'blue',   (1982, 510000)),
    (2020, 569353, "🎨 James St North — reconversion artistique (2015)",      'purple', (2002, 590000)),
]


CITY_NAME = "Québec, Québec"
CITY_COLOR = '#002395'

years = [1860, 1870, 1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950,
         1960, 1970, 1980, 1990, 2000, 2010, 2020]

population = [51109, 59699, 62446, 63090, 68840, 78015, 95193, 130594,
              150757, 184769, 250000, 480000, 576075, 645550, 682757,
              765706, 839311]

annotations = [
    (1860, 51109,  "🚢 Port bois équarri — 2e port Amérique Nord (1850)",      'brown',  (1862, 120000)),
    (1870, 59699,  "🔥 Grands incendies 1845 — Saint-Roch rasé (1845)",        'red',    (1872, 190000)),
    (1900, 68840,  "🏰 Château Frontenac — tourisme de prestige (1893)",       'orange', (1882, 250000)),
    (1910, 78015,  "😡 Émeutes conscription — 4 morts (1918)",                 'darkred',(1902, 310000)),
    (1920, 95193,  "🌉 Pont de Québec — 2 effondrements (1919)",               'gray',   (1922, 350000)),
    (1960, 250000, "✊ Révolution tranquille — PQ 1968 (1960)",                'blue',   (1942, 400000)),
    (1980, 576075, "🏛️ UNESCO patrimoine mondial (1985)",                      'gold',   (1962, 580000)),
    (2020, 839311, "🎮 Ubisoft Québec — économie du savoir (2010)",            'purple', (2002, 870000)),
]

CITY_NAME = "Calgary, Alberta"
CITY_COLOR = '#CC0000'

years = [1860, 1870, 1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950,
         1960, 1970, 1980, 1990, 2000, 2010, 2020]

population = [0, 0, 500, 3876, 4392, 43704, 63305, 83761,
              88904, 129060, 249641, 403319, 592743, 710677,
              879003, 1096833, 1336000]

annotations = [
    (1880, 500,    "🏇 Fort Calgary — Police montée (1875)",                  'red',    (1862, 200000)),
    (1890, 3876,   "🚂 CPR arrive — boom immédiat (1883)",                    'brown',  (1872, 350000)),
    (1910, 43704,  "🐄 Stampede fondé — 'Sandstone City' (1912)",            'orange', (1892, 500000)),
    (1930, 83761,  "💀 Dirty Thirties — sécheresse et faillites (1930)",     'gray',   (1912, 650000)),
    (1950, 129060, "🛢️ Pétrole Leduc — QG pétrolier Canada (1947)",          'black',  (1932, 750000)),
    (1980, 592743, "😡 PEN Trudeau — alienation de l'Ouest (1980)",          'darkred',(1962, 850000)),
    (1990, 710677, "🏔️ Jeux olympiques d'hiver Calgary (1988)",              'blue',   (1972, 950000)),
    (2020, 1336000,"🏗️ Studio Bell + New Library — diversification (2018)",  'purple', (2002, 1400000)),
]


CITY_NAME = "Edmonton, Alberta"
CITY_COLOR = '#003F87'

years = [1860, 1870, 1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950,
         1960, 1970, 1980, 1990, 2000, 2010, 2020]

population = [0, 0, 700, 1000, 4176, 31064, 58821, 79197,
              93817, 159631, 337568, 495702, 657057, 839924,
              937845, 1159869, 1418118]

annotations = [
    (1880, 700,    "🏰 Fort Edmonton — CBH poste de traite (1795)",           'brown',  (1862, 280000)),
    (1900, 4176,   "⛏️ Ruée Klondike — porte du Nord (1897)",                 'gold',   (1872, 450000)),
    (1910, 31064,  "🏛️ Capitale Alberta — Université fondée (1905)",          'blue',   (1882, 600000)),
    (1930, 79197,  "💀 Dépression — sécheresse Prairies (1930)",              'gray',   (1912, 750000)),
    (1950, 159631, "🛢️ Puits Leduc No.1 — pétrole albertain (1947)",          'black',  (1932, 850000)),
    (1980, 657057, "🏬 West Edmonton Mall — plus grand monde (1981)",         'orange', (1962, 950000)),
    (2010, 1159869,"🏒 ICE District — Rogers Place — renouveau (2016)",       'blue',   (1992, 1200000)),
    (2020, 1418118,"🤖 Institut Amii — capitale IA canadienne (2017)",        'purple', (2002, 1480000)),
]

CITY_NAME = "Laval, Québec"
CITY_COLOR = '#0057A8'

years = [1860, 1870, 1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950,
         1960, 1970, 1980, 1990, 2000, 2010, 2020]

population = [18000, 20000, 22000, 25000, 30000, 35000, 42000, 55000,
              72000, 100000, 155000, 228010, 268335, 314398,
              343005, 401553, 438366]

annotations = [
    (1860, 18000,  "⛪ Île Jésus — seigneurie Sulpiciens (1636)",             'brown',  (1862, 80000)),
    (1900, 30000,  "🌾 Grenier maraîcher de Montréal (1900)",                 'green',  (1882, 120000)),
    (1940, 72000,  "🚗 Premiers ponts — suburbanisation débute (1914)",       'orange', (1922, 160000)),
    (1960, 155000, "💥 Baby-boom — croissance la plus rapide Canada (1955)",  'red',    (1942, 210000)),
    (1970, 228010, "🏙️ Fusion 14 municipalités — Ville de Laval (1965)",     'blue',   (1952, 260000)),
    (1990, 314398, "😡 Vaillancourt — corruption systémique (1989)",          'darkred',(1972, 340000)),
    (2010, 401553, "🚇 Métro prolongé à Laval (2007)",                        'green',  (1992, 420000)),
    (2020, 438366, "🏒 Place Bell — identité culturelle propre (2017)",       'purple', (2002, 460000)),
]

CITY_NAME = "London, Ontario"
CITY_COLOR = '#4B0082'

years = [1860, 1870, 1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950,
         1960, 1970, 1980, 1990, 2000, 2010, 2020]

population = [11000, 18000, 31000, 37983, 46300, 58850, 60959, 71148,
              78264, 95343, 169569, 223222, 283668, 315000,
              336539, 366151, 422324]

annotations = [
    (1860, 11000,  "🚂 Grand Trunk Railway — nœud ferroviaire (1853)",        'brown',  (1862, 120000)),
    (1870, 18000,  "🍺 Labatt fondée — manufacturing boom (1847)",            'gold',   (1872, 180000)),
    (1900, 46300,  "📋 London Life — capital des assurances (1874)",          'navy',   (1882, 220000)),
    (1920, 60959,  "⚔️ WWI — Royal Canadian Regiment (1914)",                'gray',   (1902, 260000)),
    (1950, 95343,  "🏭 GM, Kellogg's, 3M — âge d'or manufacturier (1950)",   'green',  (1932, 310000)),
    (1980, 283668, "📉 Désindustrialisation — fermetures usines (1975)",      'red',    (1962, 350000)),
    (2000, 336539, "🎓 Western U — santé et éducation (1990)",                'purple', (1982, 390000)),
    (2020, 422324, "💔 Attaque islamophobe — solidarité nationale (2021)",    'black',  (2002, 440000)),
]

CITY_NAME = "Longueuil, Québec"
CITY_COLOR = '#006400'

years = [1860, 1870, 1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950,
         1960, 1970, 1980, 1990, 2000, 2010, 2020]

population = [3500, 4200, 5000, 5800, 6500, 8000, 11000, 18000,
              25000, 40000, 80000, 128857, 124320, 129874,
              128016, 231409, 239700]

annotations = [
    (1860, 3500,   "⚔️ Fort Le Moyne — seigneurie Charles Le Moyne (1657)", 'brown',   (1862, 60000)),
    (1870, 4200,   "🌉 Pont Victoria — premier pont Saint-Laurent (1859)",  'blue',    (1872, 90000)),
    (1940, 25000,  "✈️ Pratt & Whitney s'installe à Longueuil (1928)",      'navy',    (1922, 110000)),
    (1960, 80000,  "🚗 Pont Champlain — explosion suburbaine (1962)",       'orange',  (1942, 145000)),
    (1970, 128857, "🚇 Métro prolongé — 1 seule station (1967)",            'green',   (1952, 170000)),
    (1980, 124320, "📉 Défusions annoncées — chaos municipal (1980)",       'red',     (1962, 195000)),
    (2010, 231409, "🏙️ Méga-fusion puis défusions (2002-2006)",            'purple',  (1992, 245000)),
    (2020, 239700, "🚆 REM — nouveau pont Champlain (2019)",                'teal',    (2002, 255000)),
]

CITY_NAME = "Sherbrooke, Québec"
CITY_COLOR = '#8B0000'

years = [1860, 1870, 1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950,
         1960, 1970, 1980, 1990, 2000, 2010, 2020]

population = [5800, 7227, 9906, 11765, 16405, 16405, 23515, 28603,
              35965, 50543, 66554, 80711, 74075, 76429,
              75845, 154601, 172950]

annotations = [
    (1860, 5800,   "🌊 Force hydraulique Magog — 'Manchester du Canada' (1852)", 'blue',   (1862, 55000)),
    (1870, 7227,   "🚂 Grand Trunk — jonction Portland-Montréal (1852)",         'brown',  (1872, 70000)),
    (1900, 16405,  "🧵 Textile dominant — Paton, Penman's (1890)",               'orange', (1882, 90000)),
    (1940, 35965,  "⚔️ Guerre — basculement francophone 60% (1941)",            'gray',   (1922, 110000)),
    (1960, 66554,  "🎓 Université de Sherbrooke fondée (1954)",                  'green',  (1942, 130000)),
    (1980, 74075,  "📉 Fermetures textiles — départ anglophones (1977)",         'red',    (1962, 145000)),
    (2010, 154601, "🏙️ Méga-fusion — 6 villes absorbées (2002)",               'purple', (1992, 160000)),
    (2020, 172950, "⚛️ Institut quantique — IBM, Google (2017)",                'teal',   (2002, 178000)),
]

CITY_NAME = "Saskatoon, Saskatchewan"
CITY_COLOR = '#DAA520'

years = [1860, 1870, 1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950,
         1960, 1970, 1980, 1990, 2000, 2010, 2020]

population = [0, 0, 500, 113, 4500, 28000, 25739, 43291,
              43027, 53268, 95526, 126449, 154210, 186058,
              196811, 222189, 266141]

annotations = [
    (1880, 500,    "🙏 Colonie tempérance méthodiste fondée (1882)",          'purple', (1862, 80000)),
    (1890, 113,    "🌾 Rébellion Riel — Batoche à 90 km (1885)",             'red',    (1872, 120000)),
    (1910, 28000,  "💥 Boom blé — croissance la + rapide du Canada (1905)",  'gold',   (1892, 160000)),
    (1930, 43291,  "🌵 Dust Bowl — Grande Dépression dévaste (1930)",        'brown',  (1912, 200000)),
    (1960, 95526,  "⚗️ Potasse découverte — réserves mondiales (1943)",      'green',  (1942, 220000)),
    (1970, 126449, "🏥 Assurance-maladie Tommy Douglas (1962)",              'blue',   (1952, 235000)),
    (2000, 196811, "📉 Cycles matières premières — exode rural (1990)",      'orange', (1982, 248000)),
    (2020, 266141, "⛏️ Mine Jansen BHP — 14 G$ potasse (2021)",             'teal',   (2002, 272000)),
]


CITY_NAME = "Halifax, Nova Scotia"
CITY_COLOR = '#003087'

years = [1860, 1870, 1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950,
         1960, 1970, 1980, 1990, 2000, 2010, 2020]

population = [25000, 29582, 36100, 38437, 40832, 46619, 58372, 59275,
              70488, 85589, 92511, 122035, 114594, 114455,
              359183, 390096, 439819]

annotations = [
    (1860, 25000,  "⚓ Forteresse Atlantique — Royal Navy (1749)",            'navy',   (1862, 220000)),
    (1870, 29582,  "🍁 Confédération — Halifax résiste (1867)",               'red',    (1872, 270000)),
    (1920, 58372,  "💥 Explosion Mont-Blanc — 2000 morts (1917)",             'orange', (1902, 310000)),
    (1940, 70488,  "⚔️ Bataille Atlantique — 50 000 militaires (1940)",      'gray',   (1922, 340000)),
    (1960, 92511,  "🏘️ Destruction Africville — crime racial (1964)",        'brown',  (1942, 370000)),
    (1970, 122035, "🌉 Pont MacKay — suburbanisation Dartmouth (1970)",       'blue',   (1952, 390000)),
    (2000, 359183, "🏙️ Méga-fusion HRM — Halifax+Dartmouth (1996)",         'purple', (1982, 410000)),
    (2020, 439819, "🚢 Irving 25G$ — boom immobilier (2012)",                'teal',   (2002, 450000)),
]


CITY_NAME = "Trois-Rivières, Québec"
CITY_COLOR = '#8B0000'

years = [1860, 1870, 1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950,
         1960, 1970, 1980, 1990, 2000, 2010, 2020]

population = [7000, 7570, 8670, 10254, 11634, 13691, 22367, 35450,
              42007, 46074, 53477, 55869, 50466, 49426,
              48419, 131338, 140733]

annotations = [
    (1860, 7000,   "⚒️ Forges Saint-Maurice — 1ère industrie lourde Amérique (1730)", 'brown',  (1862, 55000)),
    (1880, 8670,   "🌲 Drave Saint-Maurice — boom bois (1875)",                        'green',  (1872, 75000)),
    (1900, 11634,  "📰 Laurentide Paper — capitale papier mondial (1887)",             'blue',   (1882, 95000)),
    (1930, 35450,  "📉 Grande Dépression — papier effondré (1929)",                   'red',    (1912, 115000)),
    (1940, 42007,  "🏭 Guerre — usines papier à plein régime (1940)",                 'gray',   (1922, 130000)),
    (1970, 55869,  "🎓 UQTR fondée — Révolution Tranquille (1969)",                   'purple', (1952, 140000)),
    (2010, 131338, "🏙️ Méga-fusion — 6 villes absorbées (2002)",                     'orange', (1992, 145000)),
    (2020, 140733, "🏎️ Grand Prix + tourisme fluvial (2015)",                        'teal',   (2002, 148000)),
]

CITY_NAME = "St. John's, Newfoundland and Labrador"
CITY_COLOR = '#009A44'

years = [1860, 1870, 1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950,
         1960, 1970, 1980, 1990, 2000, 2010, 2020]

population = [25000, 29000, 32000, 40000, 45000, 48000, 52000, 55000,
              60000, 68000, 79000, 88102, 96535, 99182,
              101936, 106172, 114923]

annotations = [
    (1860, 25000,  "🐟 Morue des Grands Bancs — 500 ans de pêche (1497)",        'blue',   (1862, 72000)),
    (1880, 32000,  "🔥 Grand Incendie — ville rasée, reconstruite (1892)",        'orange', (1872, 82000)),
    (1920, 52000,  "⚔️ Beaumont-Hamel — 710 victimes en 30 min (1916)",          'red',    (1902, 90000)),
    (1930, 55000,  "🏛️ Démocratie suspendue — Commission Gov. (1934)",           'brown',  (1912, 96000)),
    (1950, 68000,  "🍁 Confédération — Joey Smallwood (1949)",                   'red',    (1932, 102000)),
    (1990, 99182,  "🎣 Moratoire morue — fin d'une civilisation (1992)",         'gray',   (1972, 108000)),
    (2000, 101936, "🛢️ Hibernia — pétrole offshore (1997)",                     'black',  (1982, 112000)),
    (2020, 114923, "⚡ Muskrat Falls — 13G$ scandale (2016)",                   'purple', (2002, 118000)),
]

CITY_NAME = "Charlottetown, Prince Edward Island"
CITY_COLOR = '#CC0000'

years = [1860, 1870, 1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950,
         1960, 1970, 1980, 1990, 2000, 2010, 2020]

population = [6700, 8807, 11373, 11806, 12080, 11220, 12418, 12361,
              14821, 18318, 18318, 19133, 25000, 28080,
              32245, 34562, 36094]

annotations = [
    (1860, 6700,  "🍁 Conférence — Berceau Confédération (1864)",          'red',    (1862, 22000)),
    (1870, 8807,  "🏛️ ÎPÉ joint la Confédération (1873)",                 'brown',  (1872, 26000)),
    (1880, 11373, "🌾 Land Purchase Act — fin landlords (1875)",           'green',  (1882, 28000)),
    (1910, 11220, "📉 Exode rural — jeunes vers Boston (1900)",            'gray',   (1892, 30000)),
    (1960, 18318, "📚 UPEI + Holland College fondés (1969)",               'blue',   (1942, 32000)),
    (1970, 19133, "👧 Anne of Green Gables — tourisme japonais (1960)",    'purple', (1952, 33000)),
    (2000, 32245, "🌉 Pont Confederation — 12,9 km (1997)",                'orange', (1982, 34000)),
    (2020, 36094, "🦞 Gastronomie + immigration boom (2015)",              'teal',   (2002, 37000)),
]

CITY_NAME = "Winnipeg, Manitoba"
CITY_COLOR = '#003F87'

years = [1860, 1870, 1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950,
         1960, 1970, 1980, 1990, 2000, 2010, 2020]

population = [300, 1500, 7985, 25639, 42340, 136035, 179087, 218785,
              229045, 254056, 276041, 540262, 564473, 616790,
              671274, 730018, 827318]

annotations = [
    (1860, 300,    "🦬 Fort Garry — traite fourrures CBH (1821)",              'brown',  (1862, 580000)),
    (1870, 1500,   "⚖️ Riel — Manitoba Act — province (1870)",                'red',    (1872, 620000)),
    (1880, 7985,   "🚂 CPR arrive — Gateway to the West (1881)",              'blue',   (1882, 660000)),
    (1910, 136035, "🌾 Bourse des grains — 3e ville Canada (1908)",           'gold',   (1892, 695000)),
    (1920, 179087, "✊ Grève générale — naissance NPD (1919)",                'red',    (1902, 725000)),
    (1960, 276041, "🌊 Floodway — Duff's Ditch (1962)",                      'teal',   (1942, 755000)),
    (1970, 540262, "🏙️ Unicity — 13 villes fusionnées (1972)",              'orange', (1952, 780000)),
    (2010, 730018, "🏒 Jets de retour + Musée droits (2011)",                'blue',   (1992, 800000)),
    (2020, 827318, "🪶 MMIW — crise autochtone urbaine (2014)",              'purple', (2002, 815000)),
]

CITY_NAME = "Moncton, New Brunswick"
CITY_COLOR = '#002395'

years = [1860, 1870, 1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950,
         1960, 1970, 1980, 1990, 2000, 2010, 2020]

population = [1000, 3000, 5032, 8765, 11345, 16984, 23981, 27334,
              30903, 40711, 47393, 47891, 54743, 57010,
              61046, 69074, 79470]

annotations = [
    (1860, 1000,  "🚂 ICR — ateliers ferroviaires des Maritimes (1871)",    'blue',   (1862, 58000)),
    (1880, 5032,  "🏳️ Convention — drapeau acadien choisi (1881)",         'gold',   (1872, 63000)),
    (1900, 11345, "📦 Eaton's hub — distribution Maritimes (1895)",         'brown',  (1882, 67000)),
    (1940, 30903, "✈️ RCAF Moncton — formation pilotes alliés (1940)",     'gray',   (1892, 71000)),
    (1960, 47393, "🎓 Université de Moncton fondée (1963)",                 'blue',   (1942, 74000)),
    (1970, 47891, "⚖️ NB bilingue — Loi langues officielles (1969)",       'red',    (1952, 76000)),
    (1990, 57010, "📞 Centres d'appels bilingues — boom (1990)",            'teal',   (1972, 77000)),
    (2020, 79470, "🌍 Immigration francophone africaine (2015)",            'orange', (2002, 80000)),
]


CITY_NAME = "Virginia Beach, Virginia"
CITY_COLOR = '#003087'

years = [1860, 1870, 1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950,
         1960, 1970, 1980, 1990, 2000, 2010, 2020]

population = [500, 800, 1200, 1600, 2100, 3800, 6000, 9000,
              15000, 42000, 85218, 172106, 262199, 393069,
              425257, 437994, 459470]

annotations = [
    (1860, 500,   "⚓ Cape Henry — 1er débarquement anglais (1607)",        'brown',  (1862, 340000)),
    (1880, 1200,  "🌊 1er hôtel balnéaire — resort town (1883)",            'blue',   (1872, 360000)),
    (1910, 3800,  "✈️ NAS Oceana — base navale aérienne (1940)",            'navy',   (1882, 375000)),
    (1940, 15000, "🚢 U-boats — tankers coulés en vue (1942)",              'gray',   (1892, 390000)),
    (1960, 85218, "🏙️ Fusion Virginia Beach + Princess Anne (1963)",       'green',  (1942, 405000)),
    (1970, 172106,"🏠 Boom suburban — GI Bill — lotissements (1965)",       'orange', (1952, 415000)),
    (1990, 393069,"🦭 SEAL Team Six — Dam Neck (1980)",                     'red',    (1972, 425000)),
    (2020, 459470,"🌊 Montée des eaux — sunny day flooding (2010)",         'teal',   (2002, 445000)),
]

CITY_NAME = "New York City, New York"
CITY_COLOR = '#003087'

years = [1860, 1870, 1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950,
         1960, 1970, 1980, 1990, 2000, 2010, 2020]

population = [1174779, 1478103, 1911698, 2507414, 3437202, 4766883,
              5620048, 6930446, 7454995, 7891957, 7781984, 7894862,
              7071639, 7322564, 8008278, 8175133, 8336817]

annotations = [
    (1860, 1174779,  "🗽 Canal Érié — port dominant Amérique (1825)",          'blue',   (1862, 6500000)),
    (1880, 1911698,  "🌉 Brooklyn Bridge — chef-d'œuvre (1883)",               'brown',  (1872, 6800000)),
    (1890, 2507414,  "🗿 Statue Liberté + Ellis Island (1886)",                'green',  (1882, 7100000)),
    (1910, 4766883,  "🔥 Triangle Shirtwaist — 146 mortes (1911)",             'red',    (1892, 7400000)),
    (1930, 6930446,  "🏙️ Empire State + Crash Wall Street (1929)",            'gold',   (1902, 7650000)),
    (1970, 7894862,  "🎤 Stonewall + hip-hop Bronx (1969)",                   'purple', (1952, 7900000)),
    (1980, 7071639,  "💸 Faillite NYC — Bronx en feu (1975)",                  'red',    (1962, 8050000)),
    (2000, 8008278,  "💔 11 septembre — 2 977 morts (2001)",                   'gray',   (1982, 8150000)),
    (2020, 8336817,  "😷 COVID — épicentre mondial (2020)",                    'black',  (2002, 8250000)),
]

CITY_NAME = "Gatineau, Québec"
CITY_COLOR = '#003DA5'

years = [1860, 1870, 1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950,
         1960, 1970, 1980, 1990, 2000, 2010, 2020]

population = [3000, 4500, 6500, 9000, 13000, 18000, 24000, 29000,
              35000, 48000, 65000, 95000, 118000, 190000,
              226696, 261772, 291041]

annotations = [
    (1860, 3000,  "🌲 E.B. Eddy — empire allumettes et papier (1851)",     'green',  (1862, 220000)),
    (1900, 13000, "🔥 Grand incendie — 15 000 sans-abri (1900)",           'red',    (1872, 235000)),
    (1920, 24000, "🏭 Papier journal — usines tournent 24h (1915)",        'brown',  (1882, 245000)),
    (1950, 48000, "🏛️ Fonction publique fédérale — boom (1945)",          'blue',   (1892, 252000)),
    (1970, 95000, "⚖️ Loi langues officielles — franco = atout (1969)",   'gold',   (1942, 258000)),
    (1990, 190000,"🏛️ Musée civilisations — Cardinal (1989)",             'teal',   (1952, 265000)),
    (2000, 226696,"🃏 Casino Hull + fusion municipale (2002)",             'purple', (1972, 272000)),
    (2020, 291041,"🏗️ Boom immobilier — immigration franco (2015)",       'orange', (2002, 280000)),
]


CITY_NAME = "Sturgeon Falls, Ontario"
CITY_COLOR = '#006400'

years = [1860, 1870, 1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950,
         1960, 1970, 1980, 1990, 2000, 2010, 2020]

population = [100, 200, 500, 1200, 2500, 4200, 5500, 6200,
              6800, 7200, 7500, 7000, 6800, 6500,
              6266, 5932, 5750]

annotations = [
    (1880, 500,   "🚂 CPR — le rail crée le village (1882)",               'brown',  (1862, 6800)),
    (1900, 2500,  "🌲 Usine pâte à papier — Spanish River (1898)",         'green',  (1872, 7000)),
    (1910, 4200,  "🚫 Règlement 17 — interdit français (1912)",            'red',    (1882, 7200)),
    (1930, 6200,  "🏭 Abitibi Paper — empire papetier (1928)",             'gray',   (1892, 7300)),
    (1950, 7200,  "📰 Apogée — 1000 emplois usine (1950)",                 'gold',   (1902, 7350)),
    (1970, 7000,  "📉 Déclin papier journal — exode jeunes (1970)",        'orange', (1952, 7300)),
    (2000, 6266,  "💀 Fermeture usine Abitibi — 500 emplois (2002)",       'red',    (1972, 7200)),
    (2020, 5750,  "🏳️ Résilience franco — télétravail (2015)",            'blue',   (2002, 6100)),
]


CITY_NAME = "Yellowknife, Northwest Territories"
CITY_COLOR = '#FFD700'

years = [1860, 1870, 1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950,
         1960, 1970, 1980, 1990, 2000, 2010, 2020]

population = [0, 0, 0, 0, 0, 0, 0, 200,
              1000, 3500, 6000, 9483, 11000, 15179,
              16541, 19234, 20340]

annotations = [
    (1930, 200,   "⛏️ Découverte or — rush minier (1934)",                'gold',   (1932, 17000)),
    (1940, 1000,  "☢️ Radium Port Radium — projet Manhattan (1942)",      'green',  (1942, 17500)),
    (1950, 3500,  "🔄 Mines rouvrent — boom d'après-guerre (1945)",       'brown',  (1952, 18000)),
    (1970, 9483,  "🏛️ Capitale TNO — gouvernement (1967)",               'blue',   (1962, 18500)),
    (1990, 15179, "💣 Grève Giant Mine — 9 morts (1992)",                 'red',    (1972, 19000)),
    (2000, 16541, "💎 Mine Ekati — diamants canadiens (1998)",            'cyan',   (1982, 19500)),
    (2010, 19234, "☠️ Giant Mine fermée — 237kt arsenic (2004)",          'gray',   (1992, 20000)),
    (2020, 20340, "🔥 Évacuation totale — feux de forêt (2023)",          'orange', (2002, 20200)),
]

CITY_NAME = "North Bay, Ontario"
CITY_COLOR = '#1B4F8A'

years = [1860, 1870, 1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950,
         1960, 1970, 1980, 1990, 2000, 2010, 2020]

population = [0, 0, 500, 2500, 6000, 9000, 12000, 16000,
              18000, 23000, 30000, 49187, 51268, 55405,
              52771, 53651, 51553]

annotations = [
    (1880, 500,   "🚂 CPR — jonction ferroviaire fondatrice (1882)",       'brown',  (1862, 46000)),
    (1900, 6000,  "⛏️ Rush argent Cobalt — North Bay transit (1903)",      'silver', (1872, 47500)),
    (1920, 12000, "✈️ Aéroport — BCATP pilotes Commonwealth (1940)",      'blue',   (1882, 49000)),
    (1950, 23000, "🛡️ NORAD souterrain — guerre froide (1963)",           'gray',   (1892, 50000)),
    (1970, 49187, "🎓 Nipissing University College fondé (1967)",          'green',  (1942, 50500)),
    (1990, 55405, "📉 Base militaire réduite — choc emplois (1989)",       'red',    (1952, 51000)),
    (2000, 52771, "🏛️ Nipissing University indépendante (1992)",          'gold',   (1972, 51500)),
    (2020, 51553, "🏡 Télétravail — afflux du Sud COVID (2020)",           'orange', (2002, 51000)),
]


CITY_NAME = "Dallas, Texas"
CITY_COLOR = '#006400'

years = [1860, 1870, 1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950,
         1960, 1970, 1980, 1990, 2000, 2010, 2020]

population = [678, 1200, 10358, 38067, 42638, 92104, 158976, 260475,
              294734, 434462, 679684, 844401, 904078, 1006877,
              1188580, 1197816, 1304379]

annotations = [
    (1880, 10358,  "🚂 Deux rails se croisent — Dallas née (1872)",         'brown',  (1862, 1100000)),
    (1900, 42638,  "🛢️ Spindletop — pétrole texan (1901)",                 'black',  (1872, 1150000)),
    (1910, 92104,  "🏦 Federal Reserve Dallas — hub financier (1914)",      'gold',   (1882, 1170000)),
    (1940, 294734, "✈️ Aviation guerre — North American (1941)",            'gray',   (1892, 1180000)),
    (1960, 679684, "💻 Texas Instruments — circuit intégré (1958)",         'green',  (1902, 1190000)),
    (1970, 844401, "🔫 JFK assassiné — Dealey Plaza (1963)",               'red',    (1942, 1200000)),
    (1980, 904078, "✈️ DFW ouvre — hub mondial (1974)",                    'blue',   (1952, 1210000)),
    (2020, 1304379,"🏢 Toyota, CBRE — exodus Californie (2017)",           'orange', (2002, 1250000)),
]


CITY_NAME = "San Jose, California"
CITY_COLOR = '#0066CC'

years = [1860, 1870, 1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950,
         1960, 1970, 1980, 1990, 2000, 2010, 2020]

population = [3000, 4000, 12567, 18060, 21500, 28946, 39642, 57651,
              68457, 95280, 204196, 459913, 629400, 782248,
              894943, 945942, 1013240]

annotations = [
    (1860, 3000,   "🌸 Capitale des vergers — prunes du monde (1860)",      'green',  (1862, 870000)),
    (1880, 12567,  "🚂 Southern Pacific — relie SF (1864)",                  'brown',  (1872, 880000)),
    (1940, 68457,  "⚔️ Internement japonais — Japantown vidé (1942)",       'red',    (1882, 890000)),
    (1950, 95280,  "🔬 Stanford Industrial Park — HP, tech (1951)",          'blue',   (1892, 900000)),
    (1960, 204196, "💾 Fairchild Semi — circuit intégré (1957)",             'purple', (1902, 910000)),
    (1970, 459913, "🏗️ Dutch Hamann — annexions massives (1960)",           'orange', (1942, 920000)),
    (2000, 894943, "🌐 eBay fondé — dot-com boom (1995)",                   'gold',   (1952, 930000)),
    (2020, 1013240,"🏢 Google Downtown West — ville tech (2019)",           'cyan',   (2002, 950000)),
]


CITY_NAME = "Saguenay, Québec"
CITY_COLOR = '#003DA5'

years = [1860, 1870, 1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950,
         1960, 1970, 1980, 1990, 2000, 2010, 2020]

population = [8000, 12000, 18000, 25000, 32000, 42000, 55000, 72000,
              85000, 105000, 125000, 133000, 138000, 157000,
              150000, 144000, 145000]

annotations = [
    (1860, 8000,   "🌲 Price Brothers — empire du bois (1838)",             'green',  (1862, 130000)),
    (1880, 18000,  "🚂 Chemin de fer Québec–Lac-Saint-Jean (1888)",         'brown',  (1872, 132000)),
    (1920, 55000,  "🏭 Pâtes et papier — Kénogami (1912)",                  'gray',   (1882, 134000)),
    (1930, 72000,  "⚡ Arvida fondée — Alcan aluminium (1926)",             'silver', (1892, 136000)),
    (1940, 85000,  "✈️ Record mondial alu — effort de guerre (1943)",       'blue',   (1902, 138000)),
    (1970, 133000, "🎓 UQAC fondée — démocratisation (1969)",               'gold',   (1942, 140000)),
    (1990, 157000, "🌊 Déluge du Saguenay — catastrophe (1996)",            'red',    (1952, 142000)),
    (2010, 144000, "🏙️ Fusion Chicoutimi-Jonquière-La Baie (2002)",        'orange', (2002, 146000)),
]


CITY_NAME = "Saint-Jean-sur-Richelieu, Québec"
CITY_COLOR = '#C8102E'

years = [1860, 1870, 1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950,
         1960, 1970, 1980, 1990, 2000, 2010, 2020]

population = [3500, 4800, 6200, 7800, 9500, 11000, 13500, 16000,
              19000, 24000, 32000, 40000, 50000, 60000,
              79600, 87000, 95000]

annotations = [
    (1860, 3500,  "⚔️ Fort Saint-Jean — axe militaire Richelieu (1666)",   'red',    (1862, 82000)),
    (1880, 6200,  "🚢 Canal de Chambly + rail — hub transit (1851)",        'blue',   (1872, 84000)),
    (1900, 9500,  "🏺 St. Johns Pottery — argile du Richelieu (1839)",      'brown',  (1882, 86000)),
    (1930, 16000, "🏭 Manufactures textiles — entre-deux-guerres (1925)",   'gray',   (1892, 88000)),
    (1960, 32000, "🎖️ CMR fondé — officiers bilingues (1952)",             'green',  (1902, 90000)),
    (1980, 50000, "🎈 Festival montgolfières — 400k visiteurs (1982)",      'orange', (1942, 91000)),
    (2000, 79600, "🏙️ Fusion — Saint-Jean absorbe Iberville (2001)",       'purple', (1952, 92000)),
    (2020, 95000, "🚗 A-35 complète — boom navetteurs Montréal (2018)",    'gold',   (2002, 96000)),
]

