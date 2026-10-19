import os

from ultralytics import YOLO


def main():
    # run from the repository folder so the relative paths in config.yaml work
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    model = YOLO("yolov8s.yaml")
    result = model.train(
    # yaml is a configuration file
        data="config.yaml",
        epochs=300,
    # Data Augmentation
        hsv_v=1,
        degrees=10,
        translate=0.1,
        scale=0.2,
        shear=2.0,
    # GPU, but additional steps are required
    # If you want to use the CPU then replace 'cuda' with 'cpu'
        device='cuda'
    )

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()  # needed for Windows
    main()
