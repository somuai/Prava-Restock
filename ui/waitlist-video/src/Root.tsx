import {Composition} from "remotion";
import {RestockFeatureFilm} from "./RestockFeatureFilm";

export const RemotionRoot = () => {
  return (
    <Composition
      id="RestockFeatureFilm"
      component={RestockFeatureFilm}
      durationInFrames={450}
      fps={30}
      width={960}
      height={1080}
      defaultProps={{
        productName: "Attikan Estate coffee",
        quoteAmount: "₹380",
      }}
    />
  );
};
