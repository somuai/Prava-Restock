import { useEffect, useState } from "react";
import type { CSSProperties } from "react";

export type RevealContent =
  | {
      kind: "product";
      image: string;
      name: string;
      scale?: number;
      bottom?: string;
    }
  | {
      kind: "award";
      logo: string;
      name: string;
      accent: string;
      scale?: number;
      bottom?: string;
    };

function awardAssetPath(logo: string, suffix = "") {
  const filename = logo.split("/").pop() || "award-base.svg";
  const slug = filename.replace(/\.(svg|png)$/i, "");
  return `/app/assets/3d/subscription-awards/${slug}${suffix}.png`;
}

export type ParcelReveal3DProps = {
  content: RevealContent;
  parcelLabel: string;
  merchantLabel: string;
};

/**
 * One coherent reveal stage: the matched premium closed/open parcel pair is
 * preloaded together, then crossfades once. There is no second WebGL parcel
 * underneath it, so the user never sees two unrelated boxes during loading.
 */
export function ParcelReveal3D({
  content,
  parcelLabel,
  merchantLabel,
}: ParcelReveal3DProps) {
  const [opened, setOpened] = useState(false);

  useEffect(() => {
    setOpened(false);
    // Leave two painted frames for the closed parcel, then begin the opening.
    // This makes the response immediate without flashing straight to the open state.
    let secondFrame = 0;
    const firstFrame = window.requestAnimationFrame(() => {
      secondFrame = window.requestAnimationFrame(() => setOpened(true));
    });
    return () => {
      window.cancelAnimationFrame(firstFrame);
      window.cancelAnimationFrame(secondFrame);
    };
  }, [content.name]);

  const visualStyle = {
    "--reveal-scale": content.scale ?? 1,
    "--reveal-bottom": content.bottom ?? "32%",
    "--reveal-accent": content.kind === "award" ? content.accent : "#1f6b56",
  } as CSSProperties;

  return (
    <section
      className="parcel-reveal parcel-reveal--premium"
      aria-label={`${content.name} opening from a Restock parcel`}
      style={visualStyle}
    >
      <div className={`parcel-visual-stage${opened ? " parcel-visual-stage--open" : ""}`} aria-hidden="true">
        <span className="parcel-floor-shadow" />
        <img
          className="parcel-photo parcel-photo--closed"
          src="/app/assets/3d/restock-parcel-closed-branded.png"
          alt=""
        />
        <img
          className="parcel-photo parcel-photo--open"
          src="/app/assets/3d/restock-parcel-open-branded.png?v=2"
          alt=""
        />

        {content.kind === "product" ? (
          <span className="parcel-floating-content parcel-floating-content--product">
            <img src={content.image} alt="" />
          </span>
        ) : (
          <span className="parcel-floating-content parcel-floating-content--award">
            <img className="parcel-award-body" src={awardAssetPath(content.logo)} alt="" />
            <img className="parcel-award-mark" src={awardAssetPath(content.logo, "-mark")} alt="" />
          </span>
        )}
        <img
          className="parcel-photo parcel-photo--open parcel-photo--front-lip"
          src="/app/assets/3d/restock-parcel-open-branded.png?v=2"
          alt=""
        />
      </div>

      <div className="parcel-label">
        <span>{parcelLabel}</span>
        <strong>{content.name}</strong>
      </div>
      <div className="parcel-source-seal">
        <span>Restock care parcel</span>
        <strong>Source · {merchantLabel}</strong>
      </div>
      <div className="parcel-route" aria-hidden="true">
        <span>packed by restock</span>
        <i />
        <span>source · {merchantLabel}</span>
      </div>
      <p className="parcel-whisper" aria-hidden="true">opened for you</p>
    </section>
  );
}

export type ProviderAward3DProps = {
  logo: string;
  accent: string;
  name: string;
  live?: boolean;
};

export function ProviderAward3D({
  logo,
  accent,
  name,
  live = false,
}: ProviderAward3DProps) {
  const awardImage = awardAssetPath(logo);
  const markImage = awardAssetPath(logo, "-mark");
  return (
    <span
      className={`provider-award-canvas provider-award-object${live ? " provider-award-object--live" : ""}`}
      aria-hidden="true"
      title={name}
      style={{ "--provider-accent": accent } as CSSProperties}
    >
      <img className="provider-award-cube" src={awardImage} alt="" />
      <span className="provider-award-mark">
        <img src={markImage} alt="" />
      </span>
    </span>
  );
}
