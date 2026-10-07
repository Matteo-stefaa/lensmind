import io

from PIL import Image, ImageStat

from lensmind.camera.mock_image import PREVIEW_SIZE, render


def luma(data: bytes) -> Image.Image:
    with Image.open(io.BytesIO(data)) as image:
        return image.convert("L")


def mean(data: bytes) -> float:
    return ImageStat.Stat(luma(data)).mean[0]


def fraction(data: bytes, low: int, high: int) -> float:
    histogram = luma(data).histogram()
    return sum(histogram[low : high + 1]) / sum(histogram)


def test_jpeg_of_requested_size() -> None:
    data = render(0.0, PREVIEW_SIZE)
    assert data[:2] == b"\xff\xd8"
    with Image.open(io.BytesIO(data)) as image:
        assert image.size == PREVIEW_SIZE


def test_brightness_increases_with_exposure() -> None:
    means = [mean(render(stops, PREVIEW_SIZE)) for stops in (-2, -1, 0, 1, 2)]
    assert all(darker < brighter for darker, brighter in zip(means, means[1:], strict=False))


def test_overexposure_clips_highlights() -> None:
    clipped_over = fraction(render(3, PREVIEW_SIZE), 250, 255)
    clipped_normal = fraction(render(0, PREVIEW_SIZE), 250, 255)
    assert clipped_over > clipped_normal + 0.1


def test_underexposure_crushes_shadows() -> None:
    crushed_under = fraction(render(-3, PREVIEW_SIZE), 0, 10)
    crushed_normal = fraction(render(0, PREVIEW_SIZE), 0, 10)
    assert crushed_under > crushed_normal + 0.05


def test_render_is_deterministic() -> None:
    assert render(0.5, PREVIEW_SIZE) == render(0.5, PREVIEW_SIZE)
