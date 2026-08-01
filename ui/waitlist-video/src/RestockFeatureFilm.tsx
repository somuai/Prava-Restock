import type {CSSProperties, ReactNode} from "react";
import {
  AbsoluteFill,
  Easing,
  Img,
  interpolate,
  Sequence,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import {bodyFont, displayFont, labelFont} from "./fonts";

const C = {
  canvas: "#f7f7f4",
  surface: "#fffefa",
  ink: "#171717",
  muted: "#686963",
  faint: "#96958d",
  line: "#ccc8c0",
  green: "#255c49",
  greenDark: "#173f31",
  greenSoft: "#dfe9e3",
  amber: "#a05f1e",
  amberSoft: "#f2e5cb",
  cardboard: "#c59a69",
};

const easeOut = Easing.bezier(0.16, 1, 0.3, 1);
const settle = Easing.bezier(0.23, 1, 0.32, 1);
const FILM_DURATION = 450;
const SCENE_DURATION = 98;
const SCENE_STARTS = [0, 88, 176, 264, 352] as const;

const clamp = {
  extrapolateLeft: "clamp" as const,
  extrapolateRight: "clamp" as const,
};

const stageNames = ["WATCHING", "RUNNING LOW", "PRICE CHECKED", "YOU CHOOSE", "RESTOCKED"];

const stageIndexAt = (frame: number) => {
  if (frame < SCENE_STARTS[1]) return 0;
  if (frame < SCENE_STARTS[2]) return 1;
  if (frame < SCENE_STARTS[3]) return 2;
  if (frame < SCENE_STARTS[4]) return 3;
  return 4;
};

const enterExit = (frame: number, duration: number) =>
  Math.min(
    interpolate(frame, [0, 10], [0, 1], {...clamp, easing: easeOut}),
    interpolate(frame, [duration - 10, duration], [1, 0], {...clamp, easing: easeOut}),
  );

const Scene = ({
  children,
  duration,
}: {
  children: ReactNode;
  duration: number;
}) => {
  const frame = useCurrentFrame();
  const visibility = enterExit(frame, duration);
  return (
    <AbsoluteFill
      style={{
        opacity: visibility,
        scale: interpolate(visibility, [0, 1], [0.975, 1], clamp),
        fontFamily: bodyFont,
      }}
    >
      {children}
    </AbsoluteFill>
  );
};

const Label = ({children, tone = "green"}: {children: ReactNode; tone?: "green" | "amber" | "neutral"}) => {
  const palette =
    tone === "amber"
      ? {background: C.amberSoft, color: C.amber}
      : tone === "neutral"
        ? {background: "rgba(255,255,255,.72)", color: C.muted}
        : {background: C.greenSoft, color: C.greenDark};
  return (
    <div
      style={{
        ...palette,
        display: "inline-flex",
        alignItems: "center",
        width: "fit-content",
        minHeight: 42,
        padding: "0 18px",
        borderRadius: 999,
        fontFamily: labelFont,
        fontSize: 20,
        letterSpacing: "0.08em",
      }}
    >
      {children}
    </div>
  );
};

const Coffee = ({size = 330, float = 0}: {size?: number; float?: number}) => (
  <Img
    src={staticFile("assets/product-coffee-attikan-cutout.png")}
    style={{
      width: size,
      height: size * 1.13,
      objectFit: "contain",
      filter: "drop-shadow(0 32px 28px rgba(23,63,49,.18))",
      translate: `0 ${float}px`,
    }}
  />
);

const Background = () => {
  const frame = useCurrentFrame();
  const drift = interpolate(frame, [0, FILM_DURATION], [-25, 25]);
  return (
    <AbsoluteFill style={{background: C.canvas, overflow: "hidden"}}>
      <AbsoluteFill
        style={{
          background:
            "radial-gradient(circle at 68% 12%, rgba(255,255,255,.96) 0, rgba(255,255,255,0) 36%), linear-gradient(145deg, #eef2ed 0%, #f7f7f4 53%, #eee7dc 100%)",
        }}
      />
      <div
        style={{
          position: "absolute",
          width: 620,
          height: 620,
          borderRadius: "50%",
          right: -210,
          top: -120,
          background: "rgba(37,92,73,.10)",
          translate: `${drift}px 0`,
        }}
      />
      <div
        style={{
          position: "absolute",
          width: 520,
          height: 520,
          borderRadius: "50%",
          left: -250,
          bottom: -210,
          background: "rgba(197,154,105,.12)",
          translate: `${-drift}px 0`,
        }}
      />
      <AbsoluteFill
        style={{
          opacity: 0.17,
          backgroundImage:
            "linear-gradient(rgba(37,92,73,.12) 1px, transparent 1px), linear-gradient(90deg, rgba(37,92,73,.12) 1px, transparent 1px)",
          backgroundSize: "48px 48px",
          maskImage: "linear-gradient(to bottom, rgba(0,0,0,.7), transparent 78%)",
        }}
      />
    </AbsoluteFill>
  );
};

const Header = () => {
  const frame = useCurrentFrame();
  const current = stageIndexAt(frame);
  return (
    <div
      style={{
        position: "absolute",
        top: 58,
        left: 64,
        right: 64,
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        zIndex: 20,
      }}
    >
      <div style={{display: "flex", alignItems: "center", gap: 13}}>
        <Img src={staticFile("assets/restock-mark.png")} style={{width: 48, height: 48, objectFit: "contain"}} />
        <div style={{fontFamily: displayFont, fontWeight: 650, fontSize: 36, letterSpacing: "-0.055em"}}>restock.</div>
      </div>
      <div style={{position: "absolute", top: 76, left: 0, right: 0, display: "flex", gap: 10}}>
        {stageNames.map((name, index) => (
          <div key={name} style={{display: "flex", flex: 1, flexDirection: "column", gap: 8}}>
            <div
              style={{
                height: 5,
                borderRadius: 999,
                background: index <= current ? C.green : "rgba(23,23,23,.12)",
              }}
            />
            <div
              style={{
                fontFamily: labelFont,
                fontSize: 14,
                letterSpacing: "0.06em",
                color: index === current ? C.greenDark : C.faint,
              }}
            >
              {name}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

const TrackedScene = () => {
  const frame = useCurrentFrame();
  const float = interpolate(frame, [0, 49, 97], [6, -4, 6], {...clamp, easing: Easing.inOut(Easing.sin)});
  return (
    <Scene duration={SCENE_DURATION}>
      <div style={sceneColumn}>
        <Label>WATCHING YOUR COFFEE</Label>
        <div style={{fontFamily: displayFont, fontSize: 66, lineHeight: 0.96, letterSpacing: "-0.055em", textAlign: "center", fontWeight: 610}}>
          Watching your coffee.
        </div>
        <Coffee size={340} float={float} />
        <div style={miniReceipt}>
          <div>
            <div style={receiptLabel}>LAST BOUGHT</div>
            <div style={receiptValue}>26 days ago</div>
          </div>
          <div style={{width: 1, alignSelf: "stretch", background: C.line}} />
          <div>
            <div style={receiptLabel}>USUAL CADENCE</div>
            <div style={receiptValue}>28 days</div>
          </div>
        </div>
      </div>
    </Scene>
  );
};

const TriggeredScene = () => {
  const frame = useCurrentFrame();
  const pulse = interpolate(frame, [0, 49, 97], [0.9, 1.02, 0.9], {...clamp, easing: Easing.inOut(Easing.sin)});
  return (
    <Scene duration={SCENE_DURATION}>
      <div style={{...sceneColumn, gap: 28}}>
        <Label tone="amber">TIME TO RESTOCK</Label>
        <div style={{position: "relative", height: 370, width: 500, display: "flex", alignItems: "center", justifyContent: "center"}}>
          <div
            style={{
              position: "absolute",
              width: 360,
              height: 360,
              borderRadius: "50%",
              background: C.amberSoft,
              scale: pulse,
              boxShadow: "0 28px 80px rgba(160,95,30,.12)",
            }}
          />
          <Coffee size={300} />
        </div>
        <div style={{display: "flex", gap: 14, width: "100%"}}>
          <div style={{...signalCard, background: C.surface}}>
            <div style={receiptLabel}>RUNNING LOW</div>
            <div style={{fontFamily: displayFont, fontSize: 46, fontWeight: 650, letterSpacing: "-0.045em"}}>2 days left</div>
          </div>
          <div style={{...signalCard, background: C.amberSoft}}>
            <div style={receiptLabel}>PRICE NOW</div>
            <div style={{fontFamily: displayFont, fontSize: 46, fontWeight: 650, letterSpacing: "-0.045em"}}>₹380 ≤ ₹400</div>
          </div>
        </div>
      </div>
    </Scene>
  );
};

const QuotedScene = () => {
  const frame = useCurrentFrame();
  const amountScale = interpolate(frame, [10, 24], [0.92, 1], {...clamp, easing: settle});
  return (
    <Scene duration={SCENE_DURATION}>
      <div style={{...sceneColumn, gap: 28}}>
        <Label>CURRENT ZEPTO PRICE</Label>
        <div style={{...paperCard, minHeight: 610}}>
          <div style={{display: "flex", alignItems: "flex-start", gap: 32}}>
            <div style={{width: 250, height: 315, borderRadius: 34, background: C.greenSoft, display: "flex", alignItems: "center", justifyContent: "center"}}>
              <Coffee size={210} />
            </div>
            <div style={{display: "flex", flexDirection: "column", gap: 18, flex: 1, paddingTop: 18}}>
              <div style={receiptLabel}>ATTIKAN ESTATE COFFEE</div>
              <div style={{fontFamily: displayFont, fontWeight: 650, fontSize: 74, letterSpacing: "-0.06em", scale: amountScale, transformOrigin: "left center"}}>₹380</div>
              <div style={{fontSize: 34, color: C.muted}}>Same 500g pack</div>
              <div style={{height: 1, background: C.line, width: "100%"}} />
              <div style={{display: "flex", justifyContent: "space-between", fontSize: 30}}>
                <span style={{color: C.muted}}>Your limit</span>
                <span style={{fontWeight: 650}}>₹1,000</span>
              </div>
            </div>
          </div>
          <div style={{height: 1, background: C.line, margin: "38px 0 30px"}} />
          <div style={{fontSize: 28, lineHeight: 1.35, color: C.muted}}>
            Price checked just now. A change above 15% would require approval again.
          </div>
        </div>
      </div>
    </Scene>
  );
};

const ApprovalScene = () => {
  const frame = useCurrentFrame();
  const selection = interpolate(frame, [34, 52], [0, 1], {...clamp, easing: settle});
  return (
    <Scene duration={SCENE_DURATION}>
      <div style={{...sceneColumn, gap: 28}}>
        <Label>NEEDS YOUR SAY</Label>
        <div style={{...paperCard, padding: 44, minHeight: 635}}>
          <div style={{display: "flex", alignItems: "center", gap: 28}}>
            <div style={{width: 190, height: 230, display: "flex", alignItems: "center", justifyContent: "center", background: C.greenSoft, borderRadius: 28}}>
              <Coffee size={160} />
            </div>
            <div style={{display: "flex", flexDirection: "column", gap: 12, flex: 1}}>
              <div style={receiptLabel}>ATTIKAN ESTATE COFFEE</div>
              <div style={{fontFamily: displayFont, fontSize: 50, fontWeight: 650, lineHeight: 1.02, letterSpacing: "-0.05em"}}>
                Coffee for ₹380
              </div>
              <div style={{fontSize: 29, color: C.muted}}>Zepto · ₹380 of your ₹1,000 limit</div>
            </div>
          </div>
          <div style={{height: 1, background: C.line, margin: "34px 0"}} />
          <div style={{fontSize: 30, color: C.muted, lineHeight: 1.35}}>
            You see the exact item, merchant, amount and cap before payment approval.
          </div>
          <div style={{display: "grid", gridTemplateColumns: "1.2fr 1fr 1fr", gap: 14, marginTop: 36}}>
            <div
              style={{
                ...buttonStyle,
                background: selection > 0.5 ? C.greenDark : C.green,
                color: "white",
                scale: interpolate(selection, [0, 1], [1, 1.045], clamp),
                boxShadow: `0 ${interpolate(selection, [0, 1], [12, 24], clamp)}px 36px rgba(23,63,49,.24)`,
              }}
            >
              {selection > 0.74 ? "Approved" : "Approve"}
            </div>
            <div style={{...buttonStyle, border: `1px solid ${C.line}`, background: C.surface}}>Adjust</div>
            <div style={{...buttonStyle, border: `1px solid ${C.line}`, background: C.surface}}>Skip</div>
          </div>
        </div>
      </div>
    </Scene>
  );
};

const PravaBoundary = () => {
  const frame = useCurrentFrame();
  const progress = interpolate(frame, [0, 28], [0, 1], {...clamp, easing: settle});
  return (
    <div
      style={{
        position: "absolute",
        left: 84,
        right: 84,
        bottom: 134,
        minHeight: 126,
        display: "flex",
        alignItems: "center",
        gap: 24,
        padding: "24px 28px",
        borderRadius: 28,
        color: "white",
        background: C.greenDark,
        opacity: progress,
        translate: `0 ${interpolate(progress, [0, 1], [40, 0], clamp)}px`,
        boxShadow: "0 24px 60px rgba(23,63,49,.24)",
      }}
    >
      <Img src={staticFile("assets/restock-mark-white.png")} style={{width: 64, height: 64, objectFit: "contain"}} />
      <div style={{display: "flex", flexDirection: "column", gap: 7}}>
        <div style={{fontFamily: labelFont, fontSize: 18, letterSpacing: "0.08em", color: "#cce4d8"}}>APPROVED WITH PRAVA</div>
        <div style={{fontFamily: displayFont, fontSize: 38, lineHeight: 1, fontWeight: 620}}>Passkey approval confirmed</div>
      </div>
    </div>
  );
};

const RestockedScene = () => {
  const frame = useCurrentFrame();
  const lift = interpolate(frame, [0, 34, 97], [28, -28, -18], {...clamp, easing: settle});
  return (
    <Scene duration={SCENE_DURATION}>
      <div style={{...sceneColumn, gap: 18}}>
        <div style={{position: "relative", width: 710, height: 510, display: "flex", alignItems: "center", justifyContent: "center"}}>
          <Img
            src={staticFile("assets/3d/restock-parcel-open-branded.png")}
            style={{
              position: "absolute",
              width: 700,
              height: 525,
              objectFit: "contain",
              bottom: -54,
              filter: "drop-shadow(0 34px 42px rgba(23,23,23,.14))",
            }}
          />
          <div style={{position: "absolute", top: 10, zIndex: 3}}>
            <Coffee size={245} float={lift} />
          </div>
        </div>
        <div style={{fontFamily: displayFont, fontSize: 60, fontWeight: 650, letterSpacing: "-0.055em", textAlign: "center", lineHeight: 0.98}}>
          Restocked.<br />Watching again.
        </div>
        <div style={{fontSize: 29, color: C.muted}}>Next expected check in 28 days</div>
      </div>
    </Scene>
  );
};

const sceneColumn: CSSProperties = {
  position: "absolute",
  top: 210,
  left: 84,
  right: 84,
  bottom: 112,
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  justifyContent: "center",
  gap: 24,
};

const miniReceipt: CSSProperties = {
  width: "100%",
  display: "grid",
  gridTemplateColumns: "1fr 1px 1fr",
  gap: 30,
  padding: "30px 38px",
  background: C.surface,
  border: `1px solid ${C.line}`,
  borderRadius: 26,
  boxShadow: "0 22px 55px rgba(23,23,23,.07)",
};

const paperCard: CSSProperties = {
  width: "100%",
  padding: 48,
  borderRadius: 34,
  border: `1px solid ${C.line}`,
  background: C.surface,
  boxShadow: "0 28px 72px rgba(23,23,23,.09)",
};

const signalCard: CSSProperties = {
  flex: 1,
  display: "flex",
  minHeight: 145,
  flexDirection: "column",
  justifyContent: "center",
  gap: 10,
  padding: 28,
  borderRadius: 28,
  border: `1px solid ${C.line}`,
  boxShadow: "0 20px 45px rgba(23,23,23,.07)",
};

const receiptLabel: CSSProperties = {
  fontFamily: labelFont,
  fontSize: 18,
  letterSpacing: "0.08em",
  color: C.muted,
};

const receiptValue: CSSProperties = {
  marginTop: 8,
  fontFamily: displayFont,
  fontSize: 36,
  fontWeight: 630,
  letterSpacing: "-0.04em",
};

const buttonStyle: CSSProperties = {
  height: 76,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  borderRadius: 999,
  fontFamily: displayFont,
  fontSize: 27,
  fontWeight: 650,
};

export const RestockFeatureFilm = (_props: {productName: string; quoteAmount: string}) => {
  return (
    <AbsoluteFill style={{fontFamily: bodyFont, color: C.ink, overflow: "hidden"}}>
      <Background />
      <Header />
      <Sequence from={SCENE_STARTS[0]} durationInFrames={SCENE_DURATION} premountFor={30}>
        <TrackedScene />
      </Sequence>
      <Sequence from={SCENE_STARTS[1]} durationInFrames={SCENE_DURATION} premountFor={30}>
        <TriggeredScene />
      </Sequence>
      <Sequence from={SCENE_STARTS[2]} durationInFrames={SCENE_DURATION} premountFor={30}>
        <QuotedScene />
      </Sequence>
      <Sequence from={SCENE_STARTS[3]} durationInFrames={SCENE_DURATION} premountFor={30}>
        <ApprovalScene />
        <Sequence from={58} durationInFrames={40} premountFor={15}>
          <PravaBoundary />
        </Sequence>
      </Sequence>
      <Sequence from={SCENE_STARTS[4]} durationInFrames={SCENE_DURATION} premountFor={30}>
        <RestockedScene />
      </Sequence>
    </AbsoluteFill>
  );
};
