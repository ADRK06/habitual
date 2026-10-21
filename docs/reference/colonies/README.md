# Colonies — exact UI reference

Exported from the approved design canvas "Habitual Colonies — Planet Views". This is the SOURCE OF TRUTH for how every screen looks. Match it exactly.

## What is here
- `screens/*.dc.html` — one file per screen (32). Each is plain HTML with inline styles: every colour, font, font-size, padding, gap, border and size is written out. `Web*` = 1440x900, `Phone*` = 390x844. `Sidebar`, `PhoneHud`, `PhoneNav` are shared components used by the other screens.
- `art/*.png` — the real pixel-art sprites (80 files), referenced by the screens as `../art/<id>.png`. Keep `image-rendering: pixelated`.
- `canvas.json` — screen titles and layout (which screens are interactive).
- `ART_MANIFEST` section below — what each sprite is.

## How to read a `.dc.html`
- Ignore `<x-dc>`, `<helmet>`, `<script type="text/x-dc">`, `<sc-for>`, `<sc-if>`, `{{holes}}`, `<dc-import>`: that is the design tool's templating. Treat `<sc-for>` as a loop, `<sc-if>` as a condition, `{{x}}` as a variable, `<dc-import name="Sidebar">` as an include of `screens/Sidebar.dc.html`.
- The inline `style="..."` values are the spec. Port them 1:1 into Tailwind classes or component CSS (use arbitrary values like `w-[358px]` where needed). Do not "improve", round, or re-theme.
- Interactive screens (avatar locker, planet customizer, habits, shop, etc.) contain the behaviour in the `<script>` block (`renderVals`, `setState`): selection state, locked/owned/price badges, shuffle, "use free parts". Reproduce that behaviour with Alpine/HTMX.
- Fonts: Silkscreen, IBM Plex Sans, IBM Plex Mono (Google Fonts link at the top of each file).
- Copy text in the screens (e.g. "Good evening, Commander", "SHIELD UP") is sample data, replace with real data but keep the same formatting, casing and length behaviour.

## Rules
1. Pixel-match the screens at their stated sizes (390 and 1440 wide). Between those sizes, scale fluidly without changing the look.
2. No extra shadows, gradients, rounded corners, or new colours. Corners are square.
3. Use only the sprites in `art/`. If a sprite is needed that is not here (for example building level 2 or 3, a damaged or scaffold variant), draw it in the same style with `scripts/make_sprites.py` (same palette, same pixel density) and show it for approval first.
4. When a real data screen cannot match a mock because data is missing, say so and propose; do not invent a different layout.

## ART_MANIFEST

| file in art/ | what it is (alt text or code name) | used in |
|---|---|---|
| 02dbdb774a0f77db580c7e678aaf164b.png | Meera's green planet Verdant Prime with buildings on its curve | PhoneGalaxy.dc.html, PhoneVisit.dc.html, WebGalaxy.dc.html |
| 03365443777eff054045b5d9dac735d5.png | emb_bolt | PhoneAvatar.dc.html, WebAvatar.dc.html |
| 0cdb2907aa4a5d6ecaadeee5f0f71fdd.png | Observatory | PhoneVisit.dc.html, WebHabits.dc.html, WebHome.dc.html, WebLanding.dc.html |
| 10722e334b81662e8e390429f06572d1.png | (see usage) | PhoneShop.dc.html, WebShop.dc.html |
| 11daf5aa9d7ea8282bb0028766db8332.png | Pixel-art planet with buildings on its curve, an orbit ring, a station and a moon | Globe.dc.html, PhoneBuild.dc.html, PhoneCheckIn.dc.html, PhoneHome.dc.html, WebHome.dc.html |
| 11f0eec12d484e79f789516b33535718.png | face_1 | PhoneAvatar.dc.html, WebAvatar.dc.html |
| 14731d8dd44af7d5dddc283de3c64dff.png | acc_scarf | PhoneAvatar.dc.html, WebAvatar.dc.html |
| 1e2e9540656ad1457862546a15a49ae8.png | hel_crest | CustomizeFlow.dc.html, PhoneAvatar.dc.html, WebAvatar.dc.html |
| 1fabd52e32f8f8dd07b0b0d0752c6666.png | Pixel-art floating island seen from above at an angle, with a tower, lab, dome, reactor and a landing pad | Isometric.dc.html |
| 2538c776edc28cec59ec00fd00ec7e67.png | suit_steel | CustomizeFlow.dc.html, PhoneAvatar.dc.html, WebAvatar.dc.html |
| 2672b4085bc1fcbfd158512e350f24a8.png | vis_signal | PhoneAvatar.dc.html, WebAvatar.dc.html |
| 289c5fc29cb8b515285b0bfee0e05397.png | suit_signal | PhoneAvatar.dc.html, WebAvatar.dc.html |
| 298555d524aba6902f97d2c4a2a58659.png | hel_round | PhoneAvatar.dc.html, WebAvatar.dc.html |
| 2be38c0f38ebc9ca1c8ebf5014baa243.png | (see usage) | WebFleet.dc.html |
| 2ea50d01c4a051b24d2d2ed395eee6b2.png | acc_lights | PhoneAvatar.dc.html, WebAvatar.dc.html |
| 36def7fece835ab90b181af91fba641d.png | (see usage) | PhoneHome.dc.html, PhoneStorm.dc.html, WebHome.dc.html, WebSector.dc.html |
| 3e907169335ccd71aac4cf55104041ae.png | moon1 | PhonePlanet.dc.html, WebPlanet.dc.html |
| 3f89991e301e8f2318496819a501707e.png | icon | PhonePlanet.dc.html, WebPlanet.dc.html |
| 41326809df27d06e781b9363b010be29.png | Power Reactor | PhoneVisit.dc.html, WebHabits.dc.html, WebHome.dc.html, WebLanding.dc.html |
| 4223c94e73e4e4dac74903a0d8c8d629.png | amber | PhonePlanet.dc.html, WebPlanet.dc.html |
| 48a95d329198f9ce6ab40073e37f56c6.png | gas | PhonePlanet.dc.html, WebPlanet.dc.html |
| 49a78cf50d20b7c7dd7cf6b600d0e4db.png | Your planet in a storm with rain streaks, lightning and a damaged Research Lab | PhoneStorm.dc.html, WebLanding.dc.html |
| 4c5e10db8669c8059784d445cf039584.png | hair_dark | PhoneAvatar.dc.html, WebAvatar.dc.html |
| 4d588aa9c02b7c0e2c3c866ccb44702b.png | moon2 | PhonePlanet.dc.html, WebPlanet.dc.html |
| 60a3210093b573549153066d3b54b340.png | Defense Tower | PhoneHome.dc.html, PhoneVisit.dc.html, WebHabits.dc.html, WebHome.dc.html, WebLanding.dc.html |
| 60fb4991e971e63f41226a9cf9dd23a8.png | emb_star | PhoneAvatar.dc.html, WebAvatar.dc.html |
| 6261b648dbf40a50180c2fcaa97c6ae0.png | emb_planet | PhoneAvatar.dc.html, WebAvatar.dc.html |
| 626fe13583f9a1beb6007ffbda45f638.png | icon | PhonePlanet.dc.html, WebPlanet.dc.html |
| 67b48b54adece8d0fb6cab429b885ac4.png | hair_silver | PhoneAvatar.dc.html, WebAvatar.dc.html |
| 6c9b90961eec1ad3adbe5cbfe0e1d67d.png | (see usage) | WebHabits.dc.html, WebHome.dc.html, WebLanding.dc.html |
| 6efbd6f23459283465d454ef1462c333.png | icon | PhonePlanet.dc.html, WebPlanet.dc.html |
| 7086c715151fb0500e83b582a3f74636.png | Research Lab | PhoneHome.dc.html, PhoneLanding.dc.html, PhoneVisit.dc.html, WebHabits.dc.html, WebHome.dc.html, WebLanding.dc.html |
| 760890681407fd130e89f534c2172ee1.png | rust | PhonePlanet.dc.html, WebPlanet.dc.html |
| 79e56d4d28c9262a4f55a088dc37004e.png | (see usage) | PhoneHabits.dc.html, PhoneLanding.dc.html, PhoneShop.dc.html, WebHabits.dc.html, WebShop.dc.html |
| 7b857b3fc6c3bd250ba08b75d04f35ce.png | steel | PhonePlanet.dc.html, WebPlanet.dc.html |
| 7cd110ccc7734053d1495017f80ff716.png | icon | PhonePlanet.dc.html, WebPlanet.dc.html |
| 81ef5c02121224f3c7346f4e45f4957b.png | Your fleet's space station under a green shield, with three member ships firing at a rust-red alien mothership | PhoneFleet.dc.html, PhoneVisit.dc.html, WebFleet.dc.html, WebLanding.dc.html |
| 8c8d464038b047da68fb3c6139d2cede.png | icon | PhonePlanet.dc.html, WebPlanet.dc.html |
| 8ea52548bcc030ffac88d685d779441f.png | Galaxy map of commanders' planets on a faint sector grid, with dotted lines linking your fleet's planets and two dim inactive planets | PhoneGalaxy.dc.html, WebGalaxy.dc.html |
| 8ebf9d7c0689e7ef15d3d48210042491.png | Pixel-art colony skyline on a rust-red horizon, with a ringed gas giant and a station in the sky | SideView.dc.html |
| 93037739eedb431e18db41628feb2b0b.png | (see usage) | CustomizeFlow.dc.html, PhoneLanding.dc.html, Sidebar.dc.html, WebLanding.dc.html, WebShop.dc.html |
| 93402df64f2c97ed352a6561c722ac2d.png | suit_phosphor | PhoneAvatar.dc.html, WebAvatar.dc.html |
| 93df6d126fa5db88f6a484ba662a35e6.png | (see usage) | PhoneShop.dc.html, WebShop.dc.html |
| a11f3f0cac003d310f29b745eec375e8.png | (see usage) | PhoneShop.dc.html, WebGalaxy.dc.html, WebShop.dc.html |
| a1f2e3fc19eefca69d0fcbfa02c10bc6.png | suit_admiral | PhoneAvatar.dc.html, WebAvatar.dc.html |
| a4246740bde6b380895b7266d5d6466c.png | lava | PhonePlanet.dc.html, WebPlanet.dc.html |
| a49c8be4f123caf1241570b87ad85534.png | ringFront | PhonePlanet.dc.html, WebPlanet.dc.html |
| ae60e6d9ea2a0512ed25744ce1785732.png | face_3 | PhoneAvatar.dc.html, WebAvatar.dc.html |
| b12e2c7e5fac8fffaf78fff031708aac.png | face_5 | PhoneAvatar.dc.html, WebAvatar.dc.html |
| bb09e50a7fa4013431420c12b99d4a05.png | acc_antenna | PhoneAvatar.dc.html, WebAvatar.dc.html |
| bbaaf9fb712684cd9db1c3f9cb4f74bd.png | (see usage) | PhoneLanding.dc.html, PhoneSector.dc.html, PhoneVisit.dc.html, WebProfile.dc.html, WebSector.dc.html |
| be71b5ddb2529eaf18e90727318d3f40.png | vis_steel | PhoneAvatar.dc.html, WebAvatar.dc.html |
| bf01f9dcb3281707e0f38a15c42e7656.png | stars | PhonePlanet.dc.html, WebPlanet.dc.html |
| bf8d74b260d1e8e0c2a502a37dae9605.png | icon | PhonePlanet.dc.html, WebPlanet.dc.html |
| c1169d1e9288fa06a86a82ffe472ea7a.png | signal | PhonePlanet.dc.html, WebPlanet.dc.html |
| c1eb4904d6f173742a80b39109755a4d.png | A pixel-art rust planet with buildings on its curve, an orbit ring and a station | PhoneLanding.dc.html, WebLanding.dc.html |
| c4860f60abb4f71879b4f183fd75594f.png | face_4 | PhoneAvatar.dc.html, WebAvatar.dc.html |
| c6bf7d33b90715c0e84c3efdd9627d16.png | ice | PhonePlanet.dc.html, WebPlanet.dc.html |
| ca34c774ae955365dba0e5415ed7f321.png | dust | PhonePlanet.dc.html, WebPlanet.dc.html |
| d0a2fc6b3fae6078ff34a477486cd36d.png | hair_brown | PhoneAvatar.dc.html, WebAvatar.dc.html |
| d459bd90b32dc1a43a5c382c723b224d.png | verdant | PhonePlanet.dc.html, WebPlanet.dc.html |
| d87c116e3245189550fc21b92f9c6428.png | Biodome | PhoneHome.dc.html, PhoneVisit.dc.html, WebHabits.dc.html, WebHome.dc.html, WebLanding.dc.html |
| dc95025ff87e47e448588afb1dc62b14.png | hel_box | PhoneAvatar.dc.html, WebAvatar.dc.html |
| ddbb09d12bad5326962e0f00afa7965f.png | vis_amber | CustomizeFlow.dc.html, PhoneAvatar.dc.html, WebAvatar.dc.html |
| de6e443848ae54303110acc720d90c2f.png | face_2 | PhoneAvatar.dc.html, WebAvatar.dc.html |
| f041a441b0216fc56652e90008dd6066.png | acc_jetpack | CustomizeFlow.dc.html, PhoneAvatar.dc.html, WebAvatar.dc.html |
| f271c681c59843dadf8671f85e529162.png | vis_rust | PhoneAvatar.dc.html, WebAvatar.dc.html |
| f2caa9ab50aef03355f99c2e25688da8.png | suit_bone | PhoneAvatar.dc.html, WebAvatar.dc.html |
| f52a95d0bece393d18b6ae7b3736e389.png | Lancer ship | WebShop.dc.html |
| f571fa0d6ce756b259e0ead2ba74c9b8.png | ringBack | PhonePlanet.dc.html, WebPlanet.dc.html |
| f7bb44468497b64667e7ba1e084c84c8.png | Commander wearing the Signal suit | PhoneVisit.dc.html, WebShop.dc.html |
| f8ab377810ed9880ab9e9ce31ea480b0.png | vis_mirror | PhoneAvatar.dc.html, WebAvatar.dc.html |
| fda5c80c9eef2e7a17d948ec9e53f848.png | Commander avatar | Globe.dc.html, Isometric.dc.html, PhoneHud.dc.html, PhoneProfile.dc.html, SideView.dc.html, Sidebar.dc.html, WebProfile.dc.html |