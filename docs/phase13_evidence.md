# Phase 13 evidence

- EWMA remains the only production forecast and is still recalibrated only after a
  completed Home purchase.
- Cold-start category priors are explicit and explainable.
- Forecast observations include predicted/actual date, category, optional quantity and
  household size, trigger cause, action, error, and model version.
- Storage requires an active `forecasting` consent record and has a dedicated delete API.
- Offline evaluation reports MAE, trigger precision, missed-depletion rate, and action rate.
- UCI Online Retail II is CC BY 4.0 but is labeled weak and benchmark-only.
- dunnhumby is blocked pending an explicit training-license review; its source page
  describes household data but does not itself establish the required license.
- The specific Kaggle mirror used for two static category priors is labeled
  CC0-1.0 on its data card; the checked-in result includes a reproducible
  extractor, hashes, method, and aggregate counts. Raw-data redistribution and
  model training remain blocked until the original-source terms receive
  authoritative review.
- No unrelated retail dataset is represented as a production human-behavior model.
