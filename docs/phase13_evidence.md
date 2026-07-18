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
- Instacart 2017 data is blocked until an authoritative current training/redistribution
  license is located.
- No unrelated retail dataset is represented as a production human-behavior model.
