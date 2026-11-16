"""Listing texts in the shapes produced by select-all + copy on common Swedish sites.

The facts are invented, but the layouts follow the real sites: Hemnet puts labels and
values on separate lines and the price without a label, Booli and agents put them on
one line.
"""

HEMNET_STYLE = """Hoppa till innehåll
Sök bostad
Ringvägen 12, 3 tr
Södermalm, Stockholms kommun
4 250 000 kr
Antal rum
2 rum
Boarea
54,5 m²
Balkong
Ja
Våning
3 av 5, hiss finns
Byggår
1929
Förening
BRF Segelflygaren
Visa föreningen
Avgift
3 245 kr/mån
Driftkostnad
4 800 kr/år
Pris/m²
77 982 kr/m²
Energiklass
D

Välkommen till denna ljusa och välplanerade tvåa högt upp i huset. Lägenheten har ett nyrenoverat kök från 2021 med induktionshäll och diskmaskin. Vardagsrummet vetter mot en lugn innergård. Badrummet är helkaklat. Föreningen är ekonomiskt stabil enligt mäklaren.

Visningar
Söndag 14:00
"""

BOOLI_STYLE = """Booli
Kungsholmsgatan 8
Kungsholmen, Stockholm
Utgångspris 3 950 000 kr
Boarea 41 m²
Rum 1,5 rum
Avgift 2 410 kr/mån
Våning 1 tr
Byggår 1937
Bostadsrättsförening Brf Byamännen 2
Hiss Nej
Balkong Nej
Publicerad 12 oktober 2025
"""

AGENT_STYLE = """Objektsbeskrivning
Adress: Storgatan 3A
Område: Bagarmossen
Utgångspris: 2 995 000 kr
Antal rum: 3
Boarea: ca 71 kvm
Våningsplan: Bottenvåning
Uteplats/balkong: Uteplats i söderläge
Månadsavgift: 4 102 kr
I avgiften ingår: värme, vatten, bredband
Byggnadsår: 1953
Förening: Bostadsrättsförening Friheten Bagarmossen
Energiklass: C
"""
