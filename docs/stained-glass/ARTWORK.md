# Stained-glass artwork and generation prompts

Generated with the **built-in image-generation tool**, using extracted frames from
the user's `Nativity Window_TV_H.mp4` as style references. The reference is
1920×1080, 30 fps, 4:26.667 long. Reviewed samples at 0.5, 26.667, 66.667,
133.333, 200 and 240 seconds.

The selected vocabulary is saturated cobalt/ultramarine and violet, turquoise
highlights, black lead outlines, cloudy marbled glass, and warm gold accents.
The centre tree adds emerald glass and ruby ornaments. The long-pointed
Bethlehem star connects it to the video's opening composition.

## Saved assets

All paths below are relative to the repository root.

| File | Purpose | Original generated dimensions |
|---|---|---|
| `eyes/graphics/stained-glass/tree.png` | Transparent tree and star | 1065×1477 RGBA |
| `eyes/graphics/stained-glass/sclera.png` | Blue-violet glass around each iris | 1774×887 RGB |
| `eyes/graphics/stained-glass/iris.png` | Gold unwrapped iris material | 2172×724 RGB |

The tree and material textures are the generated assets. The full-window shader
fills each entire rectangular panel with blue-violet glass, forming animated
eye contours within that pattern and wrapping the iris strip around each
dark blue glass pupil. The tree is surrounded by a complete glass background.

`tree-panes.png` is a **shader data map**, not visible artwork. It encodes
per-pane phase, vertical centre and validity. `tools/build_glass_panes.py`
rebuilds it deterministically from the tree's black leading. The associated
JSON records the detected panes. The runtime loads these files and performs
no image generation or segmentation.

## Tree prompt

Reference frames: 26.667 seconds and 240 seconds. Transparent background enabled.

Use case: stylized-concept. Asset type: a production Christmas tree sprite for a three-window house projection. The two attached images are STYLE REFERENCES, not edit targets. Match the references' specific stained-glass rendering extremely closely: rich saturated cobalt and ultramarine blues, violet, cyan-turquoise, emerald and golden yellow, black fairly thick smooth hand-shaped lead came outlines, luminous cloudy streaked/marbled translucent glass, subtle darker shading at pane edges, almost front-on flat stained-glass artwork, NOT 3D beveled jewels, NOT photorealistic church photography. Create ONE elegant Christmas evergreen tree entirely made from irregular curved and triangular emerald, teal and turquoise glass panes. Silhouette is a recognizable full graceful Christmas tree, with five descending branching tiers, wide base, short brown-and-gold trunk. A long-pointed golden Bethlehem star like the first reference sits just above the tree tip, joined to it, with white-gold inner facets and four long main rays (lower vertical ray longest) and four short diagonal rays. Warm gold garland winds in three graceful bands across the tree; a few ruby-red and gold round ornaments, each made of a few glass panes. Keep all internal contours outlined in black lead, preserving the references' painterly swirling glass grain rather than smooth gradients or flat vector fill. Tree should have about 45 to 65 large readable glass panes, not hundreds of tiny fragments. Single isolated tree with its star, centered, straight-on, complete silhouette visible, roughly 65% image width and 90% image height, substantial transparent margins, portrait canvas. NO enclosing window, NO frame, NO background scenery, NO floor, NO backdrop glass, NO letters, NO watermark, NO glow spill outside the silhouette. Background genuinely transparent. The goal is an asset that visually belongs beside the supplied Nativity stained-glass video.

## Blue-violet glass prompt

Reference frame: 240 seconds. Opaque output.

Use case: stylized-concept. Asset type: production UV texture for an animated stained-glass eyeball, NOT a finished eye illustration. Input image is a STYLE REFERENCE. Create a seamless rectangular material texture, landscape 2:1 aspect ratio, entirely filled edge-to-edge with stained-glass panes closely matching the reference video's cobalt/ultramarine/violet/turquoise stained glass. No central object. Rich saturated cobalt blue and deep ultramarine dominate 65%, violet and purple 20%, turquoise/cyan 15%. Thick nearly black smooth lead came joins separate about 45-65 irregular curved polygon panes, each about 1/8 image width, in an organic patchwork like the outer background of the reference. Keep every pane separately distinct. Glass has visibly flowing cloudy white-blue and purple-blue marbled streaks, light shining through color; dark subtly shaded rims next to the black lead, rich luminosity, NOT shiny faceted gemstones, NOT a church photo, NOT flat vector fills, NO metallic bevels. The same visual weight of black outlines and hand-made cloudy marbling as the reference. Flat front view, evenly luminous everywhere, NO vignette and NO perspective. Seamless left-right tileable if possible. No frame, no border, no text, no icons, no eyes, no star, no characters. Fully opaque.

## Gold iris prompt

Reference frame: 26.667 seconds. Opaque output.

Use case: stylized-concept. Asset type: an unwrapped annular UV texture for the IRIS of an animated stained-glass eye. Reference image is STYLE ONLY. Create a landscape rectangular image, 4:1 aspect ratio, full bleed. This image is a FLAT STRIP that code wraps around a circular pupil: horizontal X means the angular direction around the pupil, vertical Y means distance outward from pupil. Do NOT draw any eye or circle. Image must be filled with about 30 narrow upright gold-glass columns separated by thick smooth nearly-black slightly irregular vertical lead lines running top-to-bottom, with 2 staggered curved horizontal dividers crossing the strip to make 3 uneven tiers of small glass panes. Use radiant honey-gold, amber, lemon yellow, warm ivory, occasional burnt-orange panes and only 3-4 pale turquoise panes near the lower third. Match the reference's thick black lead outlines, glowing cloudy marbled translucent glass with little flowing swirls within each pane, slightly darker edges around each pane. NO gemstone bevels, NO metallic chrome, NO photoreal church photograph, NO flat vector fill. The top and bottom edges of the strip must have continuous thin black lead bands (about 2% image height) forming pupil border and iris rim when mapped. Keep the strip evenly lit, no vignette, no gradients across whole image. Full-bleed texture only, no symbols, no words, no frame, no pupil drawn, no eye drawn, no border beyond the two black horizontal lead bands. Make the left/right endpoints match as well as possible for wrapping.

