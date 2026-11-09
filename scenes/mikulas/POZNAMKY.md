# Poznámky ke scéně `mikulas`

Zasněžená náves o Mikuláši za soumraku. Krajina je `web/backdrops/mikulas.js`
(statické vrstvy se kreslí jednou do plátna, živé jsou hvězdy, kouř z komínů,
mihotání oken a lucerny, světýlka na vánočním stromě, jiskry ve sněhu a padající
sníh: nejvzdálenější vločky v `draw()`, bližší v `drawFront()` nad tvory).
Tvorové jdou po třech dráhách před kulisou (y 0,70 / 0,815 / 0,93); všechno, co
stojí na zemi (strom, lucerny, sněhuláci, plot), má patu nad 0,69, takže je tvor
nikdy nepřekreslí zezadu. Vyšlapaná stopa přes náves je `pathX()` z backdropu,
trasy v `render.js` ji sledují.

## Tvorové

Tři lidské postavy z `tools/make_mikulas.py` (stavebnice `tools/humanoid.py`),
protože hotový CC0 humanoid z bokorysu nejde vybarvit (viz CREDITS.md). Každá
má stejnou kostru (Hips, Spine, Chest, Neck, Head, ruce, nohy s Foot/Toe) a klipy
`Walk`, `Run`, `Idle`, `LookAround`, `Wave` (role `play`), anděl a čert i `Jump`.
Mikuláš neskáče: drží berlu a nese pytel.

- **Kostra nese tvar klidové pózy.** Pravá ruka s berlou/vidlemi je v klidu už ohnutá
  dopředu, ne tyčová póza; klipy jen natáčejí kosti. Pravá strana je -X, ta se vidí
  v bokorysu předlohy, proto drží hůl pravá ruka.
- **Chůze drží chodidla na zemi:** kyčle klesají podle skutečné délky nohou
  (`gait()` v make_mikulas.py), takže prokluz je nulový a není co ladit v `stride_rate`.
- **Čepice, vous, svatozář, rohy a čelist mají vlastní kosti** (`Mitre`, `Hair`,
  `Halo`, `Horn`, `Jaw`). Důvod: oko předlohy se odvozuje z obalky kosti `Head`;
  s čepicí a vousem v ní by skončilo mimo obličej.
- **Materiály = vnitřní linky předlohy.** Každý díl, který má jít vybarvit zvlášť,
  je vlastní materiál. Oblast užší než ~5 mm se na listu sloučí se sousedem, proto
  jsou postavy buclaté.
- **Pózu předlohy drží `anim: Walk` + `time`** ve scene.json (čtvrtina cyklu, nohy
  rozkročené). Výchozí zbarvení (`paint`) je poskládané z obdélníků `stripes`
  s plnou šířkou a souřadnice jsou vázané na tuto pózu: po změně modelu nebo `time`
  je potřeba je znovu přečíst (u Mikuláše se z `paint.py` dokonce otočí u/v, protože
  berla před ním posune střed obrysu před oko).
- Mikuláš: `activities.run` nemá (dostojně chodí), čert se zastavuje nejméně a běhá
  nejčastěji. Poměr výšek je v `motions.walk.scale` (čert 0,78, anděl 0,805).
