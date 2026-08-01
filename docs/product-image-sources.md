# Product image sources

The living-pantry interface uses real manufacturer product photography rather
than generated packaging. These assets are included for the Restock prototype
and attribution/disclosure record. A production merchant adapter should display
the current image URL returned for the exact merchant SKU instead of relying on
these static files.

| Asset | Source | Notes |
|---|---|---|
| `product-coffee-attikan.jpg` | [Blue Tokai — Attikan Estate](https://bluetokaicoffee.com/collections/all-products-1/products/attikan-estate) | Official product image. |
| `product-amul-taaza.png` | [Amul — Taaza](https://uat.amul.com/products/amul-taaza-info.php) | Official product image. |
| `product-jk-paper.png` | [JK Paper — JK A Copier](https://www.jkpaper.com/jk-a-copier) | Official product image. |
| `product-figaro-oil.webp` | [Figaro — Extra Virgin Olive Oil](https://figarooliveoil.com/shop/extra-virgin-olive-oil/1l/) | Official product image. |
| `product-aquaguard-filter.png` | [Eureka Forbes — Genuine Filters](https://www.eurekaforbes.com/c/water-purifiers/genuine-filters) | Official product image. |
| `product-tata-salt.jpg` | [Tata Salt — Driftbasket product listing](https://driftbasket.com/product/tata-salt-1-kg/) | Real retail packshot used for the prototype; the transparent cutout is a deterministic background-removal derivative. |
| `product-surf-excel.gif` | [Surf Excel Expert White — Hydri Supermarket product listing](https://www.hydrisupermarket.com.pk/surf-excel-expert-white-detergent-powder-500gm-m22252) | Real retail packshot used for the prototype; the transparent cutout is a deterministic background-removal derivative. |
| `product-colgate-strong-teeth.jpg` | [Colgate Strong Teeth — Gandhi Bazar product listing](https://www.gandhi-bazar.com/products/colgate-strong-teeth-anticavity-toothpaste-200g) | Real retail packshot used for the prototype; the transparent cutout is a deterministic background-removal derivative. |
| `sunlit-plant-wall.jpg` | [Unsplash — Robert Katzki](https://unsplash.com/photos/green-leafed-plant-near-beige-wall-GvxNOKF_9fM) | Real photographed plants and window light used as the room ambience. |
| `cardboard-texture-cc0.png` | [ambientCG Cardboard 002 via Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Cardboard002_8K_Color.png) | CC0 cardboard color texture retained as provenance for the earlier geometry study; it is not used by the current premium parcel render. |
| `restock-parcel-open-branded.png` / `restock-parcel-closed-branded.png` | OpenAI Image Generation plus deterministic Restock-green color treatment, created for Restock | Matched premium packaging states used in one preloaded reveal stage. The Restock mark is composited into both source assets; these are Restock demo packaging concepts, not official Zepto, Swiggy, or Eureka Forbes packaging. |
| `subscription-awards/award-base.png` and provider color variants | OpenAI Image Generation plus deterministic color treatment, created for Restock | Source-authored, extruded rounded-square award object guided by the user-supplied 3D app-icon reference. |
| `providers/*.svg` | [Simple Icons](https://simpleicons.org/) | Source brand silhouettes used for the Teams subscription objects. |
| `zepto.svg` / `.png` | [Wikimedia Commons — Zepto logo](https://commons.wikimedia.org/wiki/File:Zepto_Logo.svg) | Source brand mark retained for merchant attribution where the source merchant is Zepto. |
| `geist-pixel-square.woff2` | [Geist font](https://github.com/vercel/geist-font) | Pixel-face metadata font; SIL Open Font License. |

The remaining interface typography is installed from Fontsource: Inter,
Radio Canada Big, Gloria Hallelujah, and Gaegu. The display and metadata
hierarchy intentionally follows the source site's font roles while the product
content, brand, and interaction design remain Restock's own.

Brand imagery remains owned by its respective brand. Its presence here does not
imply sponsorship or endorsement.

The transparent coffee, JK Paper, Figaro, Tata Salt, Surf Excel, and Colgate
variants were made with deterministic background removal only. The original
photographed product pixels were not redrawn or generated.

The current parcel uses a preloaded matched pair of premium closed/open raster
states in one compositor-only stage. It does not hand off from a poster to a
different WebGL box, which removes the earlier double-parcel loading artifact.
The subscription-award objects are source-authored raster media with official
provider marks layered separately so the marks remain crisp and replaceable.
