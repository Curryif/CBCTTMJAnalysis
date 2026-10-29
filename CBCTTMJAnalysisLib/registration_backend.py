# -*- coding: utf-8 -*-
"""ANTsPy backend preserving the user's SyNAggro + Kabsch + residual-field sequence."""
import os, glob, json, argparse, traceback
import nibabel as nib
import numpy as np
from scipy.ndimage import map_coordinates

LPS2RAS = np.diag([-1.0, -1.0, 1.0, 1.0])

def log(s): print(s, flush=True)

def same_geometry(a, b, tol=1e-5):
    return (a.GetSize() == b.GetSize() and np.allclose(a.GetSpacing(), b.GetSpacing(), atol=tol, rtol=0)
            and np.allclose(a.GetOrigin(), b.GetOrigin(), atol=tol, rtol=0)
            and np.allclose(a.GetDirection(), b.GetDirection(), atol=tol, rtol=0))

def align_mask(mask_path, reference_path, output_path):
    import SimpleITK as sitk
    mask, ref = sitk.ReadImage(mask_path), sitk.ReadImage(reference_path)
    if not same_geometry(mask, ref):
        log("Resampling mask to its corresponding image grid with nearest-neighbor.")
        mask = sitk.Resample(mask, ref, sitk.Transform(3, sitk.sitkIdentity),
                             sitk.sitkNearestNeighbor, 0, mask.GetPixelID())
    sitk.WriteImage(mask, output_path)
    return output_path

def vector_data(img):
    a = np.asarray(img.dataobj, dtype=np.float32)
    if a.ndim == 5:
        if a.shape[3] != 1 or a.shape[4] != 3: raise ValueError("Unexpected vector field shape: {}".format(a.shape))
        a = a[:, :, :, 0, :]
    if a.ndim != 4 or a.shape[-1] != 3: raise ValueError("Expected (I,J,K,3) field, got {}".format(a.shape))
    return a

def resample_vector_to_ref(field, field_affine, ref_shape, ref_affine):
    if tuple(field.shape[:3]) == tuple(ref_shape) and np.allclose(field_affine, ref_affine, atol=1e-4, rtol=0):
        return field.astype(np.float32)
    log("Resampling composed vector field to T1 grid in physical RAS coordinates.")
    i, j, k = np.meshgrid(np.arange(ref_shape[0]), np.arange(ref_shape[1]), np.arange(ref_shape[2]), indexing="ij")
    ijk = np.stack([i, j, k], axis=-1).reshape(-1, 3)
    world = nib.affines.apply_affine(ref_affine, ijk)
    src = nib.affines.apply_affine(np.linalg.inv(field_affine), world).T
    out = np.empty(tuple(ref_shape) + (3,), dtype=np.float32)
    for c in range(3):
        out[..., c] = map_coordinates(field[..., c], src, order=1, mode="nearest", prefilter=False).reshape(ref_shape)
    return out

def save_vector(data, affine, path):
    img = nib.Nifti1Image(np.asarray(data, dtype=np.float32), affine)
    img.header.set_intent("vector", (), name="displacement vector")
    img.header["intent_code"] = 1006
    img.header.set_xyzt_units("mm")
    nib.save(img, path)

def find_composed_field(ret, prefix, outdir):
    candidates = ([ret] if isinstance(ret, str) else []) + [prefix, prefix + "comptx.nii.gz", prefix + "comptx.nii"]
    candidates += glob.glob(prefix + "*") + glob.glob(os.path.join(outdir, "*comptx*.nii*"))
    for p in candidates:
        if not p or not os.path.isfile(p) or not p.endswith((".nii", ".nii.gz")): continue
        try:
            a = np.asarray(nib.load(p).dataobj)
            if a.ndim in (4, 5) and a.shape[-1] == 3: return p
        except Exception: pass
    raise FileNotFoundError("Could not find ANTs composed displacement field. Return={!r}, prefix={!r}".format(ret, prefix))

def run(args):
    import ants
    import SimpleITK as sitk
    os.makedirs(args.out, exist_ok=True)
    t1_mask_path = align_mask(args.t1_mask, args.t1, os.path.join(args.out, "T1_mask_on_T1_grid.nii.gz"))
    t2_mask_path = align_mask(args.t2_mask, args.t2, os.path.join(args.out, "T2_mask_on_T2_grid.nii.gz"))
    t1n, t2n = nib.load(args.t1), nib.load(args.t2)
    if len(t1n.shape) != 3 or len(t2n.shape) != 3: raise ValueError("T1 and T2 must be 3D images.")
    log("T1 shape={}, spacing={}".format(t1n.shape, t1n.header.get_zooms()[:3]))
    log("T2 shape={}, spacing={}".format(t2n.shape, t2n.header.get_zooms()[:3]))

    # 1) Existing ANTsPy SyNAggro step: fixed=T1, moving=T2.
    log("[1/5] ANTsPy SyNAggro: fixed=T1, moving=T2")
    fixed, moving = ants.image_read(args.t1), ants.image_read(args.t2)
    syn = ants.registration(fixed=fixed, moving=moving, type_of_transform="SyNAggro")
    syn_path = os.path.join(args.out, "T2_warped_img_syn.nii.gz")
    ants.image_write(ants.apply_transforms(fixed=fixed, moving=moving, transformlist=syn["fwdtransforms"], interpolator="linear"), syn_path)
    prefix = os.path.join(args.out, "T2_warp_field_compose_")
    compose_ret = ants.apply_transforms(fixed=fixed, moving=moving, transformlist=syn["fwdtransforms"], compose=prefix)
    comp_path = find_composed_field(compose_ret, prefix, args.out)
    comp_img = nib.load(comp_path)
    u_total = vector_data(comp_img).copy()
    field_affine = np.asarray(comp_img.affine, dtype=np.float64)
    # Preserve the user's established conversion of vector components to RAS.
    u_total[..., 0] *= -1.0
    u_total[..., 1] *= -1.0
    u_total = resample_vector_to_ref(u_total, field_affine, t1n.shape[:3], t1n.affine)
    field_affine = np.asarray(t1n.affine, dtype=np.float64)
    save_vector(u_total, field_affine, os.path.join(args.out, "T2_warp_field.nii.gz"))

    # 2) Existing Kabsch rigid fit from T1 sphenoid voxels and the composed field.
    log("[2/5] Kabsch rigid fitting using T1 sphenoid label {}".format(args.sphenoid_label))
    t1mask = np.asarray(nib.load(t1_mask_path).dataobj) == int(args.sphenoid_label)
    if t1mask.shape != u_total.shape[:3]: raise ValueError("T1 mask and field grid differ after alignment.")
    ijk = np.argwhere(t1mask)
    if len(ijk) < 3: raise ValueError("Too few sphenoid voxels. Check sphenoid label {}.".format(args.sphenoid_label))
    xyz = nib.affines.apply_affine(field_affine, ijk)
    dst = xyz + u_total[t1mask]
    c1, c2 = xyz.mean(axis=0), dst.mean(axis=0)
    H = (xyz-c1).T @ (dst-c2)
    U, S, Vt = np.linalg.svd(H)
    R = Vt.T @ U.T
    if np.linalg.det(R) < 0:
        Vt[-1, :] *= -1
        R = Vt.T @ U.T
    t = c2 - R @ c1
    T_ras = np.eye(4); T_ras[:3, :3] = R; T_ras[:3, 3] = t
    T_lps = LPS2RAS @ T_ras @ LPS2RAS
    rigid_path = os.path.join(args.out, "T2_nihe_rigid_transform.tfm")
    rigid = sitk.AffineTransform(3)
    rigid.SetMatrix(T_lps[:3, :3].reshape(-1).tolist())
    rigid.SetTranslation(T_lps[:3, 3].tolist())
    sitk.WriteTransform(rigid, rigid_path)

    # 3) Preserve existing SimpleITK resampling sequence and T1 output geometry.
    log("[3/5] Resampling T2 image and mask to T1 reference geometry")
    fixed_sitk, moving_sitk = sitk.ReadImage(args.t1), sitk.ReadImage(args.t2)
    t2_rigid_path = os.path.join(args.out, "T2_warped_img_nihe_rigid.nii.gz")
    t2_rigid = sitk.Resample(moving_sitk, fixed_sitk, sitk.ReadTransform(rigid_path), sitk.sitkLinear, 0.0, moving_sitk.GetPixelID())
    sitk.WriteImage(t2_rigid, t2_rigid_path)
    t2mask_sitk = sitk.ReadImage(t2_mask_path)
    t2_rigid_mask_path = os.path.join(args.out, "T2_warped_mask_nihe_rigid.nii.gz")
    t2_rigid_mask = sitk.Resample(t2mask_sitk, fixed_sitk, sitk.ReadTransform(rigid_path), sitk.sitkNearestNeighbor, 0, t2mask_sitk.GetPixelID())
    sitk.WriteImage(t2_rigid_mask, t2_rigid_mask_path)

    # 4) Preserve existing residual-field calculation.
    log("[4/5] Computing residual displacement field")
    T_inv = np.linalg.inv(T_ras); R_inv = T_inv[:3, :3]; t_inv = T_inv[:3, 3]
    shape = u_total.shape[:3]
    ii, jj, kk = np.meshgrid(np.arange(shape[0]), np.arange(shape[1]), np.arange(shape[2]), indexing="ij")
    ijk_all = np.stack([ii, jj, kk], axis=-1).reshape(-1, 3)
    xyz_all = nib.affines.apply_affine(field_affine, ijk_all).reshape(shape + (3,))
    dst_all = xyz_all + u_total
    dst_rigid = dst_all.reshape(-1, 3) @ R_inv.T + t_inv
    u_residual = dst_rigid.reshape(shape + (3,)) - xyz_all
    residual_path = os.path.join(args.out, "T2_residual_elastic_field.nii.gz")
    save_vector(u_residual, field_affine, residual_path)
    npz_path = os.path.join(args.out, "T2_residual_elastic_field_ras.npz")
    np.savez_compressed(npz_path, data=u_residual.astype(np.float32), affine=field_affine.astype(np.float64))

    # 5) Optional intensity-masked residual field, matching the existing >500 convention.
    log("[5/5] Saving intensity-masked residual field")
    t1_array_kji = sitk.GetArrayFromImage(fixed_sitk)
    mask_ijk = np.transpose(t1_array_kji > 500, (2, 1, 0))
    if mask_ijk.shape == u_residual.shape[:3]:
        masked = np.zeros_like(u_residual, dtype=np.float32)
        masked[mask_ijk] = u_residual[mask_ijk]
        save_vector(masked, field_affine, os.path.join(args.out, "T2_residual_elastic_field_mask.nii.gz"))

    report = {
        "status": "success",
        "registration": "ANTsPy SyNAggro; fixed=T1, moving=T2",
        "rigid_fit": "Kabsch on T1 sphenoid label points and composed field (preserved from user's code)",
        "vector_components": "RAS after flipping x and y components, matching user's existing code",
        "residual_field_direction_assumption": "T2-rigid -> T1 based on user's prior Slicer test; verify with surface overlap",
        "t1_shape": list(t1n.shape[:3]), "t2_shape": list(t2n.shape[:3]),
        "t1_affine_RAS": t1n.affine.tolist(), "t2_affine_RAS": t2n.affine.tolist(),
        "residual_field_shape_IJK3": list(u_residual.shape), "residual_field_affine_RAS": field_affine.tolist(),
        "rigid_transform_RAS": T_ras.tolist(), "kabsch_singular_values": S.tolist(), "kabsch_point_count": int(len(xyz)),
        "outputs": {"syn_image": syn_path, "rigid_image": t2_rigid_path, "rigid_mask": t2_rigid_mask_path,
                    "warp_field": os.path.join(args.out, "T2_warp_field.nii.gz"), "residual_field": residual_path,
                    "residual_field_npz": npz_path}
    }
    with open(os.path.join(args.out, "registration_report.json"), "w", encoding="utf-8") as f: json.dump(report, f, indent=2)
    log("Registration backend finished. Residual field: " + residual_path)
    log("ASSUMED mapping: T2-rigid -> T1. Validate using surface-distance check before interpreting results.")

def prepare_existing_field(field_path, npz_output):
    if not os.path.isfile(field_path):
        raise FileNotFoundError("Residual field not found: " + field_path)
    img = nib.load(field_path)
    data = vector_data(img)
    affine = np.asarray(img.affine, dtype=np.float64)
    if data.ndim != 4 or data.shape[-1] != 3:
        raise ValueError("Expected a 3D displacement field with three vector components.")
    if not np.all(np.isfinite(data)) or not np.all(np.isfinite(affine)):
        raise ValueError("Field contains non-finite values or invalid geometry.")
    os.makedirs(os.path.dirname(os.path.abspath(npz_output)), exist_ok=True)
    np.savez_compressed(npz_output, data=data.astype(np.float32), affine=affine)
    log("Existing residual field imported without registration.")
    log("Field shape: {}".format(tuple(data.shape)))
    log("Field affine (RAS):\n{}".format(affine))
    log("Saved RAS field cache: " + npz_output)


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--t1"); p.add_argument("--t2")
    p.add_argument("--t1-mask"); p.add_argument("--t2-mask")
    p.add_argument("--out")
    p.add_argument("--sphenoid-label", type=int, default=2); p.add_argument("--fossa-label", type=int, default=4)
    p.add_argument("--prepare-existing-field", help="Import an existing residual NIfTI field without running registration.")
    p.add_argument("--field-npz-output", help="Output path for the RAS NumPy field cache used by Slicer.")
    return p.parse_args()

if __name__ == "__main__":
    try:
        args = parse_args()
        if args.prepare_existing_field:
            if not args.field_npz_output:
                raise ValueError("--field-npz-output is required with --prepare-existing-field.")
            prepare_existing_field(args.prepare_existing_field, args.field_npz_output)
        else:
            missing = [name for name in ["t1", "t2", "t1_mask", "t2_mask", "out"] if not getattr(args, name)]
            if missing:
                raise ValueError("Missing registration arguments: {}".format(", ".join(missing)))
            run(args)
    except Exception as e:
        log("ERROR: " + str(e)); traceback.print_exc(); raise
