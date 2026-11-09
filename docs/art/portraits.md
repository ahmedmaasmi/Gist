# Character portraits

Style reference: `docs/art/style_reference.png` (retro pixel-art investigation desk; dossier ID photo).
Machine-readable list for batch generation: `docs/art/portraits.csv` (file name, prompt, negative prompt).

## Shared rules (all 31 portraits)

- **Style:** 16-bit retro pixel-art portrait, head and shoulders, facing the viewer, centred, greyscale halftone shading with a limited palette (charcoal, warm grey, cream), plain flat cream background, thin dark outline, soft light from upper left, same framing as a case-file ID photo, square 1024x1024, crisp pixels, no text, no frame, no border.
- **Negative prompt:** text, letters, watermark, signature, frame, blood, gore, weapons, colour background, photorealistic, 3D render, film or TV actor likeness.
- **Output:** `frontend/public/portraits/<file_name>` (PNG, 1024×1024; the UI scales it down with nearest-neighbour so pixels stay crisp).
- **No job-specific clothes or props.** Occupations change from case to case, so keep each character's own period look only.
- **Fictional characters:** follow the book descriptions; do not copy a film or TV actor's likeness or costume.
- **Historical people:** a period-appropriate impression, not a recreated photograph; no crime-scene details.
- **Titles stay in the displayed name** (e.g. "Sergeant Cuff", "Father Brown").

## How to use a prompt

Paste the shared **Style** sentence, then `Subject:` plus the character line below. Example (full prompt for Sherlock Holmes):

> 16-bit retro pixel-art portrait, head and shoulders, facing the viewer, centred, greyscale halftone shading with a limited palette (charcoal, warm grey, cream), plain flat cream background, thin dark outline, soft light from upper left, same framing as a case-file ID photo, square 1024x1024, crisp pixels, no text, no frame, no border. Subject: a tall thin man with a hawk-like nose, sharp grey eyes, clean-shaven, Inverness cape and deerstalker cap as in the original Paget illustrations.

Tip: generate 2–3 characters first, check that they look like one set next to the reference, then batch the rest with the same seed/settings.

## List

| # | File | Name | Kind | Subject (append to the style sentence) |
|---|---|---|---|---|
| 1 | `jack_the_ripper.png` | Jack the Ripper | historical | a Victorian gentleman in a top hat and high-collared dark coat, the face half hidden in shadow, only a thin moustache and cold eyes visible, London 1888 |
| 2 | `lizzie_borden.png` | Lizzie Borden | historical | a stern woman in her early thirties, hair pulled back tightly, high-necked dark 1890s dress with a small brooch, New England |
| 3 | `dr_hawley_crippen.png` | Dr Hawley Crippen | historical | a small mild-looking man around 48, round wire-rimmed spectacles, a large drooping moustache, wing collar and bow tie, 1910 |
| 4 | `h_h_holmes.png` | H. H. Holmes | historical | a man in his thirties with a thick curled moustache, neatly parted hair, sharp intense stare, three-piece 1890s suit |
| 5 | `william_burke.png` | William Burke | historical | a rough working man in his late thirties, long sideburns, open shirt collar, worn woollen coat and neckerchief, Edinburgh 1828 |
| 6 | `william_hare.png` | William Hare | historical | a gaunt wiry man around thirty, unkempt hair, crooked grin, patched coat and scarf, Edinburgh 1828 |
| 7 | `mary_ann_cotton.png` | Mary Ann Cotton | historical | a woman around forty, dark hair parted in the middle, plain dark Victorian dress with a white collar, calm expression, 1870s |
| 8 | `dr_thomas_neill_cream.png` | Dr Thomas Neill Cream | historical | a balding man in his forties, thick moustache, small wire spectacles, black frock coat and silk hat in hand, 1890s |
| 9 | `dr_william_palmer.png` | Dr William Palmer | historical | a portly country doctor in his thirties, mutton-chop whiskers, round face, waistcoat with a watch chain, 1850s |
| 10 | `florence_maybrick.png` | Florence Maybrick | historical | an elegant young woman in her twenties, light fair hair in an updo, high lace collar, 1880s gown, poised expression |
| 11 | `adelaide_bartlett.png` | Adelaide Bartlett | historical | a dark-haired woman around thirty, hair in a neat chignon, fitted 1880s bodice with a cameo, enigmatic look |
| 12 | `madeleine_smith.png` | Madeleine Smith | historical | a young Glasgow socialite around twenty, glossy ringlets, off-shoulder 1850s dress with a lace shawl, confident gaze |
| 13 | `sweeney_todd.png` | Sweeney Todd | legend | a lean barber with wild dark hair and heavy brows, striped shirt, leather apron, unsettling smile, Fleet Street 1840s |
| 14 | `sherlock_holmes.png` | Sherlock Holmes | fictional | a tall thin man with a hawk-like nose, sharp grey eyes, clean-shaven, Inverness cape and deerstalker cap as in the original Paget illustrations |
| 15 | `dr_john_watson.png` | Dr John Watson | fictional | a sturdy man in his thirties with a neat moustache, kind steady eyes, bowler hat and tweed Victorian suit |
| 16 | `professor_moriarty.png` | Professor Moriarty | fictional | a tall very thin older man, high domed forehead, deep-set eyes, clean-shaven pale face, rounded shoulders, black frock coat |
| 17 | `irene_adler.png` | Irene Adler | fictional | an elegant opera singer in her late twenties, dark hair upswept, high lace collar, clever amused expression, 1890s |
| 18 | `inspector_lestrade.png` | Inspector Lestrade | fictional | a small lean police inspector, sallow sharp face, dark beady eyes, bowler hat and dark overcoat |
| 19 | `mycroft_holmes.png` | Mycroft Holmes | fictional | a large heavily built man in his forties, broad face, light-grey watchful eyes, immaculate black frock coat |
| 20 | `c_auguste_dupin.png` | C. Auguste Dupin | fictional | a pale thoughtful Parisian man in his thirties, tinted green spectacles, dark cravat, 1840s frock coat |
| 21 | `sergeant_cuff.png` | Sergeant Cuff | fictional | a grizzled elderly detective, thin and grey-haired, sad steel-grey eyes, plain black suit and white cravat |
| 22 | `inspector_bucket.png` | Inspector Bucket | fictional | a stout attentive detective in middle age, black suit, one forefinger raised knowingly, shrewd eyes |
| 23 | `lady_audley.png` | Lady Audley | fictional | a young lady with pale golden curls, large innocent blue eyes, delicate features, lace-trimmed Victorian gown |
| 24 | `father_brown.png` | Father Brown | fictional | a short round-faced Catholic priest, mild owlish expression, black clerical clothes, wide-brimmed shovel hat, holding a large umbrella |
| 25 | `arsene_lupin.png` | Arsène Lupin | fictional | a dashing gentleman thief in his thirties, monocle, thin moustache, top hat and opera cape over evening dress, Paris 1900s |
| 26 | `joseph_rouletabille.png` | Joseph Rouletabille | fictional | an eager young newspaper reporter around eighteen, round head, short hair, flat cap and loosened tie, 1900s |
| 27 | `dr_henry_jekyll.png` | Dr Henry Jekyll | fictional | a respectable well-made man around fifty, smooth-shaven, kind but tired face, fine Victorian suit |
| 28 | `edward_hyde.png` | Edward Hyde | fictional | a small hunched young man with a pale face, unsettling crooked grin, oversized dark coat, menacing aura (no deformity caricature) |
| 29 | `dorian_gray.png` | Dorian Gray | fictional | a strikingly handsome young man around twenty, golden curls, flawless face, velvet aesthete jacket with a buttonhole flower |
| 30 | `count_dracula.png` | Count Dracula | fictional | a tall old man, long white moustache, aquiline nose, pale skin, all in black clothing as described in Stoker's novel (not the 1931 film look) |
| 31 | `abraham_van_helsing.png` | Abraham Van Helsing | fictional | an older Dutch professor around sixty, reddish-grey hair, broad forehead, clean-shaven, keen blue eyes, dark Victorian coat |

## Later (optional)

- v0.3 interrogation: 2 extra expressions per character (`<file>_nervous.png`, `<file>_angry.png`), same framing: 62 images.
- Map backgrounds: one per setting (12); only the manor is needed for v0.1.
