# Poznámky k tvorům scény `cretaceous`

Proč mají jednotliví tvoři v `scene.json` výjimky (pohled, oko, póza).
Přeneseno z komentářů dřívějšího `dinostanice/creatures3d.py`.

## drak3d

Drak se kresli bokorysem jako chodci, i kdyz ve scene leti. Shora z nej byla Rorschachova skvrna: rozpeti kridel je vetsi nez telo, takze po fitu na list zbyla z hlavy boule na hrane a oko skoncilo jako tecka uprostred tela. Z boku ma hlavu s rohem a otevrenou hubou, oko na spravnem miste a kridlo jako plachtu se zebry — na rozdil od pteranodona, ktery je same kridlo, ma drak dost tela a hlavy, aby ho dite poznalo. Poza je natvrdo z Death (t=0.37): drak se v nem naklani dopredu s rozepjatym kridlem, takze membrana lezi v rovine listu a ma plochu k vybarveni. Ve Flying_Idle drzi kridla podel tela a z boku z nich zbyva uzky profil.

## pteranodon3d

Ptakojester prisel bez kostry, tu mu dopisuje tools/make_pteranodon.py. Kresli se shora a natoceny tak, aby rozpeti kridel — jeho nejvetsi rozmer — leželo po sirce listu; z boku by z nej byl jen tenky profil. Proto oko nelezi pred telem, ale na ose soumernosti listu (centre_x): bbox hlavy je kvuli hrebeni nesoumerny a forward=0.5 by oko poslal mimo osu.
