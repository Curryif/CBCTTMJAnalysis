# -*- coding: utf-8 -*-
"""Export interactive PyVista HTML views for the CBCT TMJ Analysis Slicer module.

Stage 2: T1 left/right fossa surfaces split into four regions, sphenoid, and axes.
Stage 3: stage2-style local directional displacement plots plus anatomical reference.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pyvista as pv

REGION_COLORS = ["#E64B4B", "#F39C34", "#4185D6", "#8A5CC2"]
LEFT_COLORS = ["#E64B4B", "#F39C34", "#4185D6", "#8A5CC2"]
RIGHT_COLORS = ["#B72F46", "#C78325", "#2868A9", "#69449B"]
AXIS_COLORS = {"LR": "red", "AP": "green", "SI": "blue"}



def inject_annotation_modules(html_path):
    """
    将方向标注和关节窝圈选联动 JS 注入 Step 3 导出的 HTML。
    JS 文件必须与 visualization_exporter.py 放在同一目录。
    支持重复执行，不会重复插入脚本。
    """
    import re
    from pathlib import Path

    html_path = Path(html_path).resolve()
    script_dir = Path(__file__).resolve().parent

    # 优先使用本次提供的原始可用版本；兼容此前的命名方式。
    js_candidates = [
        script_dir / "wb_annotations_all_in_one(2).js",
        script_dir / "wb_annotations_all_in_one(1).js",
        script_dir / "wb_annotations_all_in_one.js",
    ]
    js_path = next((candidate for candidate in js_candidates if candidate.is_file()), None)

    if not html_path.is_file():
        raise FileNotFoundError(
            "HTML 文件不存在: {}".format(html_path)
        )

    if js_path is None:
        expected = "\n".join("  - {}".format(p.name) for p in js_candidates)
        raise FileNotFoundError(
            "找不到方向标注/圈选联动 JS 文件。请将以下任一文件放到 Python 脚本同一目录：\n{}".format(expected)
        )

    # 读取原始 JS
    js_code = js_path.read_text(encoding="utf-8-sig")

    if not js_code.strip():
        raise ValueError("JS 文件为空: {}".format(js_path))

    # 读取 HTML
    html_code = html_path.read_text(
        encoding="utf-8",
        errors="replace"
    )

    start_marker = "<!-- WB_ANNOTATION_MODULES_START -->"
    end_marker = "<!-- WB_ANNOTATION_MODULES_END -->"

    # 删除以前注入的版本，避免重复注册事件
    pattern = re.compile(
        re.escape(start_marker) + r".*?" + re.escape(end_marker),
        flags=re.IGNORECASE | re.DOTALL
    )
    html_code = pattern.sub("", html_code)

    # 构造注入内容
    injected_block = (
        "\n"
        + start_marker
        + "\n<script id=\"wb-annotations-all-in-one\">\n"
        + js_code
        + "\n</script>\n"
        + end_marker
        + "\n"
    )

    # 优先插入 </body> 之前
    body_match = re.search(
        r"</body\s*>",
        html_code,
        flags=re.IGNORECASE
    )

    if body_match:
        html_code = (
            html_code[:body_match.start()]
            + injected_block
            + html_code[body_match.start():]
        )
    else:
        # 没有 body 时，插入 </html> 之前
        html_match = re.search(
            r"</html\s*>",
            html_code,
            flags=re.IGNORECASE
        )

        if html_match:
            html_code = (
                html_code[:html_match.start()]
                + injected_block
                + html_code[html_match.start():]
            )
        else:
            html_code += injected_block

    # 保存 HTML
    html_path.write_text(html_code, encoding="utf-8")

    # 检查注入结果
    check_code = html_path.read_text(
        encoding="utf-8",
        errors="replace"
    )

    if (
        start_marker not in check_code
        or end_marker not in check_code
        or 'id="wb-annotations-all-in-one"' not in check_code
    ):
        raise RuntimeError(
            "HTML 注入检查失败: {}".format(html_path)
        )

    print(
        "[HTML MODULES] 使用 JS: {}".format(js_path),
        flush=True
    )
    print(
        "[HTML MODULES] 方向标注 + 关节窝圈选联动已注入: {}".format(
            html_path
        ),
        flush=True
    )


def read_mesh(path):
    path = Path(path)
    if not path.exists():
        return None
    mesh = pv.read(str(path))
    if mesh.n_points == 0:
        return None
    return mesh.extract_surface().triangulate().clean()


def warn_lasso_actor_collision(name, mesh):
    """
    原始 JS 用点数识别圈选输入：
      3025 点 -> flat grid
      7001~8999 点 -> fossa patch
    其他解剖 actor 若恰好落入这些范围，会被 JS 一并识别。
    """
    if mesh is None:
        return
    count = int(mesh.n_points)
    if count == 3025 or 7000 < count < 9000:
        print(
            "[LASSO WARNING] extra anatomy actor '{}' has {} points and may be "
            "mistaken for a selection actor by the original JS.".format(name, count),
            flush=True
        )


def save_html_compat(plotter, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    errors = []
    try:
        plotter.trame.export_html(str(path))
        if path.exists() and path.stat().st_size > 0:
            print("HTML saved:", path, flush=True)
            return True
    except Exception as exc:
        errors.append("plotter.trame.export_html: {}: {}".format(type(exc).__name__, exc))
    try:
        plotter.export_html(str(path))
        if path.exists() and path.stat().st_size > 0:
            print("HTML saved:", path, flush=True)
            return True
    except Exception as exc:
        errors.append("plotter.export_html: {}: {}".format(type(exc).__name__, exc))
    print("[HTML EXPORT FAILED]", flush=True)
    for err in errors:
        print(" -", err, flush=True)
    return False


def save_png(plotter, path):
    try:
        plotter.screenshot(str(path))
        if Path(path).exists() and Path(path).stat().st_size > 0:
            print("PNG saved:", path, flush=True)
    except Exception as exc:
        print("PNG export warning: {}: {}".format(type(exc).__name__, exc), flush=True)


def add_axes(plotter, out_dir):
    for name, color in AXIS_COLORS.items():
        mesh = read_mesh(out_dir / ("axis_" + name + ".vtp"))
        if mesh is not None:
            warn_lasso_actor_collision("axis_" + name, mesh)
            plotter.add_mesh(mesh, color=color, smooth_shading=True, lighting=False)


def add_region_surfaces(plotter, out_dir, opacity=0.95, show_edges=False):
    count = 0
    for side, colors in (("left", LEFT_COLORS), ("right", RIGHT_COLORS)):
        for idx, color in enumerate(colors, 1):
            mesh = read_mesh(out_dir / "{}_T1_upper_region_{}.vtp".format(side, idx))
            if mesh is None:
                continue
            warn_lasso_actor_collision("{}_T1_upper_region_{}".format(side, idx), mesh)
            plotter.add_mesh(mesh, color=color, opacity=opacity, smooth_shading=True,
                             show_edges=show_edges, edge_color="black", line_width=0.45)
            count += 1
    if count == 0:
        raise FileNotFoundError("No T1 region VTP files were found. Run Step 2 first.")


def render_stage2(out_dir):
    sphenoid = read_mesh(out_dir / "sphenoid_T1.vtp")
    if sphenoid is None:
        raise FileNotFoundError("sphenoid_T1.vtp not found; run Step 2 first.")
    plotter = pv.Plotter(window_size=(1400, 1000))
    plotter.set_background("white")
    plotter.add_text("T1 left/right fossa: four-region surfaces", font_size=14, color="black")
    plotter.add_mesh(sphenoid, color="#D5BE91", opacity=0.25, smooth_shading=True)
    add_region_surfaces(plotter, out_dir, opacity=0.98, show_edges=True)
    add_axes(plotter, out_dir)
    plotter.add_text("LR: red   AP: green   SI: blue", position="lower_left", font_size=10, color="black")
    plotter.add_axes()
    plotter.reset_camera()
    html_path = out_dir / "stage2_anatomy_regions.html"
    ok = save_html_compat(plotter, html_path)
    save_png(plotter, out_dir / "stage2_anatomy_regions.png")
    plotter.close()
    if not ok:
        raise RuntimeError("Could not export stage2 HTML. Install/repair trame, trame-vtk, and trame-vuetify in the selected external Python environment.")


def load_axes(out_dir):
    path = out_dir / "sphenoid_coordinate.json"
    if not path.exists():
        raise FileNotFoundError("sphenoid_coordinate.json not found; run Step 2 first.")
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    axes = {key: np.asarray(raw[key], dtype=np.float64) for key in ("origin", "LR", "AP", "SI")}
    for key in ("LR", "AP", "SI"):
        n = np.linalg.norm(axes[key])
        if n < 1e-10:
            raise ValueError("Invalid {} coordinate axis.".format(key))
        axes[key] /= n
    return axes


def local_patch_surfaces(out_dir, side, mode, axes, height_scale):
    # 与解剖视图使用完全相同的 read_mesh() 处理流程，保证 world_patch
    # 在解剖视图和位移视图中的点顺序一致。
    patch_path = out_dir / (side + "_world_patch.vtp")
    patch = read_mesh(patch_path)
    if patch is None:
        raise FileNotFoundError("{} not found; run Step 3 first.".format(patch_path))

    component_name = "U_" + mode
    if component_name not in patch.point_data:
        raise ValueError("{} is missing point-data array {}.".format(patch_path.name, component_name))

    pts = np.asarray(patch.points, dtype=np.float64)
    n_points = len(pts)
    n = int(round(np.sqrt(n_points)))

    # 原始圈选 JS 将 55x55=3025 个点作为平面网格和位移曲面的识别标志。
    if n * n != n_points or n_points != 3025:
        raise ValueError(
            "{} has {} points; the original lasso JS requires a 55x55 grid "
            "(3025 points). Check whether clean()/decimation changed the mesh.".format(
                patch_path.name, n_points
            )
        )

    center = pts.mean(axis=0)
    rel = pts - center
    U = (rel @ axes["LR"]).reshape(n, n)
    V = (rel @ axes["AP"]).reshape(n, n)
    values = np.asarray(patch.point_data[component_name], dtype=np.float64).reshape(n, n)
    valid = np.asarray(
        patch.point_data["Valid"] if "Valid" in patch.point_data else np.ones(n_points),
        dtype=bool
    ).reshape(n, n)

    H = np.where(valid & np.isfinite(values), values, 0.0) * float(height_scale)

    # 必须在 extract_surface/triangulate 之前绑定标量。
    # StructuredGrid 的点索引采用 Fortran 顺序，因此 point_data 使用 ravel(F)。
    base_grid = pv.StructuredGrid(U, V, np.zeros_like(U))
    surface_grid = pv.StructuredGrid(U, V, H)

    scalar_name = "U_{}_mm".format(mode)
    surface_grid.point_data[scalar_name] = np.where(
        valid & np.isfinite(values), values, np.nan
    ).ravel(order="F")
    surface_grid.point_data["Valid"] = valid.astype(np.uint8).ravel(order="F")

    # 不执行 clean()，避免合并点或改变 55x55 网格索引。
    base = base_grid.extract_surface().triangulate()
    surface = surface_grid.extract_surface().triangulate()

    if base.n_points != 3025 or surface.n_points != 3025:
        raise RuntimeError(
            "{}: generated base/surface point counts are {}/{}; expected 3025/3025. "
            "The original lasso JS cannot identify these actors.".format(
                side, base.n_points, surface.n_points
            )
        )

    if scalar_name not in surface.point_data or len(surface.point_data[scalar_name]) != surface.n_points:
        raise RuntimeError("Displacement scalars were not preserved for {} {}.".format(side, mode))

    z_range = float(np.ptp(np.asarray(surface.points)[:, 2]))
    if z_range <= 0.5:
        print(
            "[LASSO WARNING] {} {} surface z-range={:.4f}; original JS identifies "
            "the deformed surface only when z-range > 0.5. Consider increasing --scale.".format(
                side, mode, z_range
            ),
            flush=True
        )

    print(
        "[LASSO GRID] {} {}: world_patch={}, base={}, surface={}, z-range={:.4f}".format(
            side, mode, patch.n_points, base.n_points, surface.n_points, z_range
        ),
        flush=True
    )
    return base, surface, values.ravel(order="C"), valid.ravel(order="C")


def render_stage3_direction(out_dir, mode, axes, height_scale):
    left_base, left_surface, left_values, left_valid = local_patch_surfaces(out_dir, "left", mode, axes, height_scale)
    right_base, right_surface, right_values, right_valid = local_patch_surfaces(out_dir, "right", mode, axes, height_scale)
    values = np.concatenate([left_values[left_valid & np.isfinite(left_values)], right_values[right_valid & np.isfinite(right_values)]])
    vmax = max(float(np.percentile(np.abs(values), 99)) if len(values) else 1e-6, 1e-6)
    plotter = pv.Plotter(shape=(1, 3), window_size=(2400, 900))
    plotter.set_background("white")
    for col, side_name, base, surface in ((0, "LEFT", left_base, left_surface), (1, "RIGHT", right_base, right_surface)):
        plotter.subplot(0, col)
        plotter.add_text("{} local deformation ({})".format(side_name, mode), font_size=12, color="black")
        plotter.add_mesh(base, color="lightgray", opacity=0.35, show_edges=True, edge_color="gray", line_width=0.55)
        plotter.add_mesh(surface, scalars="U_{}_mm".format(mode), cmap="coolwarm", clim=(-vmax, vmax),
                         opacity=0.99, show_edges=True, edge_color="black", line_width=0.25,
                         nan_color="lightgray", scalar_bar_args={"title": "{} displacement (mm)".format(mode), "n_labels": 5})
        plotter.show_bounds(grid="back", location="outer", ticks="outside", xtitle="LR (mm)", ytitle="AP (mm)",
                            ztitle="{} displacement x{}".format(mode, height_scale), all_edges=True)
    # 第三个 renderer 必须包含两个 3025 点 world_patch 和两个 7k~9k mapped patch；
    # wb_annotations_all_in_one(2).js 通过这些点数识别圈选映射输入。
    plotter.subplot(0, 2)
    plotter.add_text("Anatomical reference: T1 regions + patches", font_size=12, color="black")
    sphenoid = read_mesh(out_dir / "sphenoid_T1.vtp")
    if sphenoid is not None:
        warn_lasso_actor_collision("sphenoid_T1", sphenoid)
        plotter.add_mesh(sphenoid, color="#D5BE91", opacity=0.28, smooth_shading=True)
    add_region_surfaces(plotter, out_dir, opacity=0.82, show_edges=False)
    add_axes(plotter, out_dir)
    selection_actor_counts = []
    for side, color in (("left", "red"), ("right", "purple")):
        # 这两个 3025 点 world_patch 是 JS 在最右侧解剖视图中识别的 PCA 平面输入。
        flat_grid = read_mesh(out_dir / (side + "_world_patch.vtp"))
        if flat_grid is None:
            raise FileNotFoundError("{}_world_patch.vtp not found.".format(side))
        if flat_grid.n_points != 3025:
            raise ValueError(
                "{}_world_patch.vtp has {} points; original lasso JS requires 3025.".format(
                    side, flat_grid.n_points
                )
            )
        plotter.add_mesh(
            flat_grid, style="wireframe", color=color, line_width=1.2,
            opacity=0.95, name="WB_FLAT_{}".format(side.upper())
        )
        selection_actor_counts.append(("flat_" + side, flat_grid.n_points))

        # 这两个 mapped fossa meshes 是 JS 在解剖视图中投影并圈选的顶点。
        mapped_path = out_dir / (side + "_T1_upper_mapped_to_T2rigid.vtp")
        mapped = read_mesh(mapped_path)
        if mapped is None:
            raise FileNotFoundError("{} not found.".format(mapped_path))
        if not (7000 < mapped.n_points < 9000):
            raise ValueError(
                "{} has {} points; original lasso JS recognizes patch actors only "
                "when 7000 < n_points < 9000.".format(mapped_path.name, mapped.n_points)
            )
        plotter.add_mesh(
            mapped, color="#E8C34A", opacity=0.20, smooth_shading=True,
            name="WB_PATCH_{}".format(side.upper())
        )
        selection_actor_counts.append(("patch_" + side, mapped.n_points))

    print("[LASSO ACTORS] anatomy renderer candidates: {}".format(selection_actor_counts), flush=True)
    plotter.add_axes()
    plotter.reset_camera()

    html_path = out_dir / "local_patch_{}_with_anatomy.html".format(mode)
    # 1. 导出原始交互式 3D HTML
    ok = save_html_compat(plotter, html_path)
    # 2. 注入方向标注 + 关节窝圈选联动模块
    if ok:
        inject_annotation_modules(html_path)

    # 3. 保存 PNG 预览图
    save_png(
        plotter,
        out_dir / "local_patch_{}_with_anatomy.png".format(mode)
    )

    plotter.close()

    if not ok:
        raise RuntimeError(
            "无法导出 {} 方向的 HTML。"
            "请检查外部 Python 环境中的 PyVista、trame 及相关依赖。".format(mode)
        )




def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", type=int, choices=(2, 3), required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--scale", type=float, default=3.0)
    args = parser.parse_args()
    out_dir = Path(args.out).expanduser().resolve()
    if not out_dir.exists():
        raise FileNotFoundError("Output folder does not exist: {}".format(out_dir))
    print("HTML visualization export stage={}; output={}".format(args.stage, out_dir), flush=True)
    if args.stage == 2:
        render_stage2(out_dir)
    else:
        axes = load_axes(out_dir)
        for mode in ("LR", "AP", "SI"):
            render_stage3_direction(out_dir, mode, axes, args.scale)
    print("HTML export finished successfully.", flush=True)


if __name__ == "__main__":
    main()
