from __future__ import annotations

import argparse
import json

from audio_features import analyze_audio, feature_vector


def main():
    parser = argparse.ArgumentParser(
        description="Extract Magic Playlist DSP features from a local audio clip."
    )
    parser.add_argument("audio")
    args = parser.parse_args()

    features = analyze_audio(args.audio)

    print(
        json.dumps(
            {
                "features": features,
                "vector": feature_vector(features).tolist(),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()