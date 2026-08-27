"""Rozměry tištěného listu.

Všechny souřadnice v projektu jsou milimetry na listu A4 na šířku; z toho
vychází předloha, rozmístění značek i srovnaná fotka.
"""

SHEET_W_MM = 297.0
SHEET_H_MM = 210.0

# Šířka obrysové linky předlohy. Dítě ji obtahuje pastelkou, takže musí být
# vidět z dálky, a zároveň se s ní počítá při čtení kresby zpátky (oko se
# nesmí dotknout obrysu, texturní maska se o linku eroduje).
LINE_MM = 0.9
