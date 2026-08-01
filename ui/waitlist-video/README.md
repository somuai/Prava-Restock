# Restock waitlist feature film

A deterministic, code-rendered product preview for the public waitlist. It uses the same Restock assets and brand tokens as the application—no generated product imagery.

The fifteen-second, silent loop shows:

1. an Attikan coffee item being tracked;
2. depletion and price signals firing together;
3. a fresh Zepto quote for ₹380 (500g) against a ₹1,000 cap;
4. Approve, Adjust, and Skip controls;
5. the Prava sandbox approval boundary; and
6. the item returning to a restocked cadence.

The film uses direct product-state labels only; it does not add promotional preview badges or a persistent disclosure footer.

```bash
npm install
npm run check
npm run poster
npm run render
```

Output:

- `out/restock-feature-demo.mp4` — 960×1080, H.264, 30fps, 15 seconds, no audio stream
- `out/restock-feature-poster.png` — frame 314, suitable for reduced-motion and video loading fallback
