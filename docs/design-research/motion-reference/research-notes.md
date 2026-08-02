# Motion reference: sneakers.charmiekapoor.com

## What was studied

The supplied sneakers reference was used as a **motion-language reference**,
not a visual or brand asset source. The visual frame was captured at 1280 ×
720 in these states:

- `01-reference-home.jpg` — calm, airy starting composition.
- `02-reference-open-90ms.jpg` — the box has opened before its product is
  visible.
- `03-reference-open-400ms.jpg` — the product rises after the box establishes
  its open state.
- `04-reference-open-1000ms.jpg` — the product has reached a quiet, suspended
  resting position.

The reference’s delivered motion uses a deliberately short staged sequence:
roughly a 210/23 spring for the lid, a 260/24 spring for the product, a
five-second ambient float, and a 3.9-second damped tag swing. Its detail
reveal uses a 500 ms curve close to `cubic-bezier(.85, 0, .3, 1)`.

## Restock translation

Restock keeps its own shelves, source-labelled product photography, brand
mark, carton, and typography. It translates the useful interaction principles
into the pantry rather than copying the reference:

- a closed parcel is painted for two animation frames, then opens immediately;
- no product appears in the first 90 ms open-box state;
- the packshot rises on a separate 660 ms reveal curve and settles above the
  front parcel wall, followed by a restrained 5.2 second float;
- static shelf items only respond with a slight perspective tilt and an
  almost imperceptible scale on hover — they never lift away from their shelf;
- paper labels use a single damped 3.9 second swing instead of continuous
  decorative wobble;
- the two motion tokens are shared by Home and Teams, so provider awards react
  like their pantry counterparts without competing with the decision content.

## Evidence

- Enlarged, no-scroll Home shelf: `14-restock-home-enlarged-final.jpg`.
- Restock parcel at 90/450/1000 ms:
  `10-restock-motion-90ms-final.jpg`,
  `11-restock-motion-450ms-final.jpg`, and
  `12-restock-motion-1000ms-final.jpg`.
- Teams shelf after motion alignment: `13-teams-shelf-motion-final.jpg`.
- Side-by-side comparison inputs:
  `15-full-view-reference-vs-restock-final.jpg`,
  `16-open-90ms-reference-vs-restock-final.jpg`, and
  `17-open-settled-reference-vs-restock-final.jpg`.
