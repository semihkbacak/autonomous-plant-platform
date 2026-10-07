from ml.anomaly_model import save_demo_anomaly_model


def main() -> None:
    path = save_demo_anomaly_model()

    print("ML anomaly model trained.")
    print(f"Saved to: {path}")


if __name__ == "__main__":
    main()