from __future__ import annotations

import base64
from typing import Dict, List, Optional

from flask import Flask, render_template, request

from matrix_utils import (
    format_matrix_as_sage,
    image_to_matrix,
    matrix_to_plot_png,
    parse_matrix_literal,
    video_to_matrices,
)

UPLOAD_LIMIT_BYTES = 50 * 1024 * 1024 
TARGET_SIZE = (50, 50)
MAX_FRAMES_DISPLAY = 25
PLOT_DEFAULT_FORM = {
    "matrix_text": "",
    "plot_title": "Before Levitt",
    "plot_vmin": "0",
    "plot_vmax": "255",
    "plot_cmap": "gray",
}
PLOT_CMAPS = [
    ("gray", "Gray"),
    ("viridis", "Viridis"),
    ("plasma", "Plasma"),
    ("magma", "Magma"),
    ("inferno", "Inferno"),
]

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = UPLOAD_LIMIT_BYTES


@app.route("/", methods=["GET", "POST"])
def index():
    image_output: Optional[str] = None
    image_error: Optional[str] = None
    video_outputs: Optional[List[Dict[str, str]]] = None
    video_error: Optional[str] = None
    plot_result: Optional[Dict[str, str]] = None
    plot_error: Optional[str] = None
    plot_form = dict(PLOT_DEFAULT_FORM)

    if request.method == "POST":
        mode = request.form.get("mode", "image")

        if mode == "image":
            file = request.files.get("image")
            if not file or file.filename == "":
                image_error = "Please choose an image to upload."
            else:
                try:
                    matrix = image_to_matrix(file.stream, size=TARGET_SIZE, rescale=True)
                    image_output = format_matrix_as_sage(matrix, variable_name="M")
                except Exception as exc:  
                    image_error = f"Failed to process image: {exc}"

        elif mode == "video":
            file = request.files.get("video")

            if not file or file.filename == "":
                video_error = "Please choose a video to upload."
            else:
                frame_skip = _safe_int(request.form.get("frame_skip"), default=1, min_value=1)
                max_frames = _safe_int(
                    request.form.get("max_frames"),
                    default=10,
                    min_value=1,
                    max_value=MAX_FRAMES_DISPLAY,
                )

                try:
                    matrices = video_to_matrices(
                        file,
                        size=TARGET_SIZE,
                        rescale=True,
                        frame_skip=frame_skip,
                        max_frames=max_frames,
                    )
                    if not matrices:
                        video_error = "No readable frames were detected in this video."
                    else:
                        video_outputs = [
                            {
                                "label": f"Frame {index}",
                                "matrix": format_matrix_as_sage(
                                    matrix, variable_name=f"M_{index:03d}"
                                ),
                            }
                            for index, matrix in enumerate(matrices, start=1)
                        ]
                except Exception as exc:  
                    video_error = f"Failed to process video: {exc}"

        elif mode == "plot":
            plot_form["matrix_text"] = request.form.get("matrix_text", "")
            plot_form["plot_title"] = request.form.get(
                "plot_title", PLOT_DEFAULT_FORM["plot_title"]
            )
            plot_form["plot_vmin"] = request.form.get(
                "plot_vmin", PLOT_DEFAULT_FORM["plot_vmin"]
            )
            plot_form["plot_vmax"] = request.form.get(
                "plot_vmax", PLOT_DEFAULT_FORM["plot_vmax"]
            )

            requested_cmap = request.form.get("plot_cmap") or PLOT_DEFAULT_FORM["plot_cmap"]
            valid_cmap_values = {value for value, _ in PLOT_CMAPS}
            if requested_cmap not in valid_cmap_values:
                requested_cmap = PLOT_DEFAULT_FORM["plot_cmap"]
            plot_form["plot_cmap"] = requested_cmap

            matrix_text = plot_form["matrix_text"]
            if not matrix_text.strip():
                plot_error = "Paste a matrix definition to generate a plot."
            else:
                try:
                    matrix = parse_matrix_literal(matrix_text)
                except ValueError as exc:
                    plot_error = str(exc)
                else:
                    try:
                        vmin_value = _parse_optional_float(
                            plot_form["plot_vmin"], field_name="vmin"
                        )
                        vmax_value = _parse_optional_float(
                            plot_form["plot_vmax"], field_name="vmax"
                        )
                    except ValueError as exc:
                        plot_error = str(exc)
                    else:
                        title_value = plot_form["plot_title"].strip() or None
                        try:
                            png_bytes = matrix_to_plot_png(
                                matrix,
                                cmap=plot_form["plot_cmap"],
                                vmin=vmin_value,
                                vmax=vmax_value,
                                title=title_value,
                            )
                        except Exception as exc:
                            plot_error = f"Failed to generate plot: {exc}"
                        else:
                            encoded = base64.b64encode(png_bytes).decode("ascii")
                            plot_result = {
                                "title": title_value or "Matrix Plot",
                                "data_url": f"data:image/png;base64,{encoded}",
                            }

    return render_template(
        "index.html",
        image_output=image_output,
        image_error=image_error,
        video_outputs=video_outputs,
        video_error=video_error,
        max_frames=MAX_FRAMES_DISPLAY,
        plot_result=plot_result,
        plot_error=plot_error,
        plot_form=plot_form,
        plot_cmaps=PLOT_CMAPS,
    )


def _safe_int(
    raw_value: Optional[str],
    *,
    default: int,
    min_value: int,
    max_value: Optional[int] = None,
) -> int:
    try:
        value = int(raw_value) if raw_value is not None else default
    except (TypeError, ValueError):
        value = default

    value = max(min_value, value)
    if max_value is not None:
        value = min(max_value, value)
    return value


def _parse_optional_float(
    raw_value: Optional[str], *, field_name: str
) -> Optional[float]:
    if raw_value is None:
        return None

    stripped = raw_value.strip()
    if not stripped:
        return None

    try:
        return float(stripped)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a number.") from exc


if __name__ == "__main__":
    port = 8000
    print(f"Starting server on http://127.0.0.1:{port}")
    app.run(debug=True, port=port)
