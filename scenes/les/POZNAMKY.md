# Poznámky k tvorům scény `les`

Testovací scéna z Quaterniova **Ultimate Animated Animal Pack** (CC0). Krajina
je zatím kopie křídové laguny.

## Všichni

Kostra nemá chodidla — noha končí kostí `*LowerLeg`. Krok se proto měří ze
špiček nohou (`FrontLowerLeg.L_end`…, viz `feetOf()` ve `web/scene3d.js`).
`stride_rate` je nastavený blízko přirozenému tempu klipu Walk (0,57–0,81 těl/s
při timeScale 1); s výchozím 0,12–0,22 ze scény by zvířata šla zpomaleně.
Psovité šelmy (liška, vlk, pejsek) jdou o kousek svižněji.

## stag

Parohy jsou samostatný mesh zavěšený na kost Head (bez skinu); import je
převádí na skin s jedinou kostí. Patří tak k hlavě, a proto obálka hlavy sahá
až do parohů — oko by skončilo u jejich kořene, `eye_bias` ho posouvá dolů
a dopředu do hlavy.
