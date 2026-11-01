/* =====================================================================
 * TMJ CBCT 位移可视化 — 完整注入脚本（All-in-One 合并版）
 * =====================================================================
 * 合并自以下三个 "_标注版" HTML 文件中实际注入的两段脚本：
 *   - local_patch_AP_with_anatomy_标注版.html
 *   - local_patch_LR_with_anatomy_标注版.html
 *   - local_patch_SI_with_anatomy_标注版.html
 *
 * 功能模块：
 *   [模块一 W3D] 3D 锚定英文标注（anterior/posterior/inside/outside/R/L）
 *                - 手动相机投影（透视/平行投影均支持）
 *                - 字号随缩放联动（0.35x–4x 钳制）
 *                - 标注位置钳制在各自 renderer 视口内，不跨区
 *                - 字体 serif 14px，与原坐标轴标注一致
 *   [模块二 SEL] 关节窝圈选联动
 *                - 在最右侧解剖视图关节窝上按住拖动画圈
 *                - 关节窝补丁顶点 -> 重采样平面 (u,v) 帧（PCA + Jacobi 特征分解）
 *                - -> 最近平面网格顶点 (55x55=3025) -> 同索引位移曲面顶点
 *                - 左侧两个位移曲面实时高亮对应区域（橙色点）
 *
 * 使用方式：
 *   1) 直接注入 HTML：在 </body> 前插入 <script> 标签包裹本文件全部代码；
 *   2) 或以 node/浏览器控制台加载后手动调用。
 *   文件方向（AP/LR/SI）自动根据 location.pathname 中的关键字选择对应
 *   LABELS 配置；如路径不含关键字，可手动设置 window.WB_LABEL_MODE。
 *
 * 脚本必须挂在 document.documentElement 上（vtk.js 挂载会清空 body）。
 * ===================================================================== */

/* ---------------------------------------------------------------------
 * 标注锚点配置（三个文件唯一差异：各视图 x0,x1,y0,y1,z0,z1 不同）
 * 坐标 = [x, y, z]（场景世界坐标）
 *   r=0 → 左侧曲面视图（R 侧，inside=-x / outside=+x）
 *   r=1 → 中间曲面视图（L 侧，镜像：inside=+x / outside=-x，已修正）
 * --------------------------------------------------------------------- */
var WB_LABELS_CONFIG = {
  AP: [
    {"t":"anterior","r":0,"p":[0.14419838354222048,-5.696965946291243,3.983820533752441]},
    {"t":"posterior","r":0,"p":[0.14419838354222048,4.94602512083441,3.983820533752441]},
    {"t":"inside","r":0,"p":[-8.179062523800411,-0.37547041272841675,3.983820533752441]},
    {"t":"outside","r":0,"p":[8.467459290884852,-0.37547041272841675,3.983820533752441]},
    {"t":"R","r":0,"p":[0.14419838354222048,-0.37547041272841675,-7.344259430167602]},
    {"t":"anterior","r":1,"p":[-0.289462082911351,-6.008862495422363,3.0972153756301952]},
    {"t":"posterior","r":1,"p":[-0.289462082911351,5.90494748164531,3.0972153756301952]},
    {"t":"inside","r":1,"p":[7.007531331809082,-0.05195750688852652,3.0972153756301952]},
    {"t":"outside","r":1,"p":[-7.586455497631784,-0.05195750688852652,3.0972153756301952]},
    {"t":"L","r":1,"p":[-0.289462082911351,-0.05195750688852652,-6.065526889790907]}
  ],
  LR: [
    {"t":"anterior","r":0,"p":[0.14419838354222048,-5.696965946291243,7.326736545562744]},
    {"t":"posterior","r":0,"p":[0.14419838354222048,4.94602512083441,7.326736545562744]},
    {"t":"inside","r":0,"p":[-8.179062523800411,-0.37547041272841675,7.326736545562744]},
    {"t":"outside","r":0,"p":[8.467459290884852,-0.37547041272841675,7.326736545562744]},
    {"t":"R","r":0,"p":[0.14419838354222048,-0.37547041272841675,-6.0]},
    {"t":"anterior","r":1,"p":[-0.289462082911351,-6.008862495422363,0.6]},
    {"t":"posterior","r":1,"p":[-0.289462082911351,5.90494748164531,0.6]},
    {"t":"inside","r":1,"p":[7.007531331809082,-0.05195750688852652,0.6]},
    {"t":"outside","r":1,"p":[-7.586455497631784,-0.05195750688852652,0.6]},
    {"t":"L","r":1,"p":[-0.289462082911351,-0.05195750688852652,-13.006367683410645]}
  ],
  SI: [
    {"t":"anterior","r":0,"p":[0.14419838354222048,-5.696965946291243,4.757493125086695]},
    {"t":"posterior","r":0,"p":[0.14419838354222048,4.94602512083441,4.757493125086695]},
    {"t":"inside","r":0,"p":[-8.179062523800411,-0.37547041272841675,4.757493125086695]},
    {"t":"outside","r":0,"p":[8.467459290884852,-0.37547041272841675,4.757493125086695]},
    {"t":"R","r":0,"p":[0.14419838354222048,-0.37547041272841675,-6.101092927157879]},
    {"t":"anterior","r":1,"p":[-0.289462082911351,-6.008862495422363,4.062654829025268]},
    {"t":"posterior","r":1,"p":[-0.289462082911351,5.90494748164531,4.062654829025268]},
    {"t":"inside","r":1,"p":[7.007531331809082,-0.05195750688852652,4.062654829025268]},
    {"t":"outside","r":1,"p":[-7.586455497631784,-0.05195750688852652,4.062654829025268]},
    {"t":"L","r":1,"p":[-0.289462082911351,-0.05195750688852652,-6.153534501791]}
  ]
};

/* 按文件名自动选择锚点配置（可被 window.WB_LABEL_MODE 覆盖） */
function WB_pickLabelMode() {
  if (window.WB_LABEL_MODE && WB_LABELS_CONFIG[window.WB_LABEL_MODE]) return window.WB_LABEL_MODE;
  var path = (typeof location !== 'undefined' ? location.pathname : '').toUpperCase();
  if (path.indexOf('_AP_') >= 0) return 'AP';
  if (path.indexOf('_LR_') >= 0) return 'LR';
  if (path.indexOf('_SI_') >= 0) return 'SI';
  return 'AP'; // 默认
}

/* =====================================================================
 * 模块一：3D 锚定英文标注
 * ===================================================================== */
(function () {
  // viewport convention: [xmin, ymin, xmax, ymax] (normalized, y from bottom)
  var LABELS = WB_LABELS_CONFIG[WB_pickLabelMode()];
  var BASE_PX = 14;          // same size as axis tick labels
  var ZMIN = 0.35, ZMAX = 4; // zoom scaling clamp

  var W3D = {
    items: null,
    refs: {},   // per renderer index: {dist, ps} captured once for zoom-relative scaling
    findPlotRenderers: function () {
      var rs = global.renderWindow.getRenderers();
      var map = {};
      for (var i = 0; i < rs.length; i++) {
        var vp = rs[i].getViewport();
        var w = vp[2] - vp[0], h = vp[3] - vp[1];
        if (w > 0.3 && w < 0.4 && h > 0.9) {
          if (vp[0] < 0.1) map[0] = rs[i];
          else if (vp[0] > 0.3 && vp[0] < 0.4) map[1] = rs[i];
        }
      }
      return map;
    },
    project: function (r, p) {
      var cam = r.getActiveCamera();
      var pos = cam.getPosition(), fp = cam.getFocalPoint(), vu = cam.getViewUp();
      var va = (cam.getViewAngle() || 30) * Math.PI / 180;
      var par = cam.getParallelProjection && cam.getParallelProjection();
      var dx = fp[0]-pos[0], dy = fp[1]-pos[1], dz = fp[2]-pos[2];
      var dl = Math.sqrt(dx*dx+dy*dy+dz*dz); dx/=dl; dy/=dl; dz/=dl;
      var rx = dy*vu[2]-dz*vu[1], ry = dz*vu[0]-dx*vu[2], rz = dx*vu[1]-dy*vu[0];
      var rl = Math.sqrt(rx*rx+ry*ry+rz*rz); rx/=rl; ry/=rl; rz/=rl;
      var ux = ry*dz-rz*dy, uy = rz*dx-rx*dz, uz = rx*dy-ry*dx;
      var vx = p[0]-pos[0], vy = p[1]-pos[1], vz = p[2]-pos[2];
      var vd = vx*dx+vy*dy+vz*dz;
      if (vd <= 0.1) return null;
      var px = vx*rx+vy*ry+vz*rz, py = vx*ux+vy*uy+vz*uz;
      var W = window.innerWidth, H = window.innerHeight;
      var vp = r.getViewport();
      var vw = vp[2]-vp[0], vh = vp[3]-vp[1];
      var aspect = (vw*W)/(vh*H);   // 宽高比必须用像素比，不能用归一化比值
      var ndx, ndy;
      if (par) {
        var ps = cam.getParallelScale ? cam.getParallelScale() : 10;
        ndx = px/(ps*aspect); ndy = py/ps;
      } else {
        var t = Math.tan(va/2);
        ndx = px/(vd*t*aspect); ndy = py/(vd*t);
      }
      var fx = vp[0] + (ndx*0.5+0.5)*vw;
      var fy = vp[1] + (ndy*0.5+0.5)*vh;
      return [fx*W, (1-fy)*H, par, vd, W, H, vp];
    },
    tick: function () {
      if (!W3D.items) { requestAnimationFrame(W3D.tick); return; }
      for (var i = 0; i < W3D.items.length; i++) {
        var it = W3D.items[i];
        var s = W3D.project(it.r, it.p);
        if (!s || s[0] < 0 || s[0] > s[4] || s[1] < 0 || s[1] > s[5]) {
          it.el.style.display = 'none';
        } else {
          var W = s[4], H = s[5], vp = s[6];
          // zoom-relative font scaling: perspective -> camera distance, parallel -> parallelScale
          var ref = W3D.refs[it.ri], sc = 1;
          if (ref) {
            if (s[2]) { // parallel
              var ps = it.r.getActiveCamera().getParallelScale ? it.r.getActiveCamera().getParallelScale() : ref.ps;
              sc = ref.ps / ps;
            } else {
              sc = ref.dist / s[3];
            }
            sc = Math.max(ZMIN, Math.min(ZMAX, sc));
          }
          it.el.style.fontSize = (BASE_PX * sc).toFixed(1) + 'px';
          // clamp inside this renderer's viewport region so labels never spill over neighbors
          var xMin = vp[0]*W + 8, xMax = vp[2]*W - 8;
          var yMin = (1-vp[3])*H + 8, yMax = (1-vp[1])*H - 8;
          var cx = Math.max(xMin, Math.min(xMax, s[0]));
          var cy = Math.max(yMin, Math.min(yMax, s[1]));
          it.el.style.display = '';
          it.el.style.left = cx + 'px';
          it.el.style.top = cy + 'px';
        }
      }
      requestAnimationFrame(W3D.tick);
    },
    start: function () {
      if (!window.global || !global.renderWindow) { setTimeout(W3D.start, 200); return; }
      var map;
      try { map = W3D.findPlotRenderers(); } catch (e) { setTimeout(W3D.start, 200); return; }
      if (!map[0] || !map[1]) { setTimeout(W3D.start, 200); return; }
      var root = document.createElement('div');
      root.id = 'wb3d-labels';
      root.style.cssText = 'position:fixed;inset:0;z-index:10;pointer-events:none;overflow:hidden;';
      document.documentElement.appendChild(root);   // 注意：不能挂 body（vtk 挂载会清空 body）
      W3D.items = [];
      LABELS.forEach(function (l) {
        var r = map[l.r];
        if (!r) return;
        if (!W3D.refs[l.r]) {
          var cam = r.getActiveCamera();
          var pos = cam.getPosition(), fp = cam.getFocalPoint();
          var d = Math.sqrt(Math.pow(fp[0]-pos[0],2)+Math.pow(fp[1]-pos[1],2)+Math.pow(fp[2]-pos[2],2));
          W3D.refs[l.r] = { dist: d, ps: (cam.getParallelScale ? cam.getParallelScale() : 10) };
        }
        var el = document.createElement('div');
        el.className = 'wb3d';
        el.textContent = l.t;
        root.appendChild(el);
        W3D.items.push({ r: r, ri: l.r, p: l.p, el: el });
      });
      requestAnimationFrame(W3D.tick);
    }
  };
  var st = document.createElement('style');
  st.textContent = '.wb3d{position:absolute;transform:translate(-50%,-50%);color:#222;'
    + 'font:normal 14px/1.2 serif;white-space:nowrap;'
    + 'text-shadow:0 0 2px #fff,0 0 4px #fff,0 0 6px #fff;pointer-events:none;}';
  document.head.appendChild(st);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', W3D.start);
  else W3D.start();
})();

/* =====================================================================
 * 模块二：关节窝圈选联动
 * 映射链：fossa patch 顶点 -> 重采样平面 (u,v) 帧（PCA）-> 最近平面网格
 *         顶点 (55x55) -> 同索引位移曲面顶点（索引对应关系已验证）
 * ===================================================================== */
(function () {
  var SEL = {
    on: false, ready: false, failed: false,
    anaR: null, patches: [], flats: [], plotR: [null, null],
    sel: [],          // {plotR, pts:[x,y,z,...], anaPts:[...]}
    poly: [], drawing: false, msgT: null
  };
  window.WSEL = SEL;

  function jacobi3(A) {
    var V = [[1,0,0],[0,1,0],[0,0,1]];
    for (var it = 0; it < 80; it++) {
      var p = 0, q = 1, mx = Math.abs(A[0][1]);
      if (Math.abs(A[0][2]) > mx) { p = 0; q = 2; mx = Math.abs(A[0][2]); }
      if (Math.abs(A[1][2]) > mx) { p = 1; q = 2; mx = Math.abs(A[1][2]); }
      if (mx < 1e-12) break;
      var App = A[p][p], Aqq = A[q][q], Apq = A[p][q];
      var tau = (Aqq - App) / (2 * Apq);
      var t = (tau >= 0 ? 1 : -1) / (Math.abs(tau) + Math.sqrt(1 + tau * tau));
      var c = 1 / Math.sqrt(1 + t * t), s = t * c;
      A[p][p] = App - t * Apq;
      A[q][q] = Aqq + t * Apq;
      A[p][q] = A[q][p] = 0;
      for (var k = 0; k < 3; k++) {
        if (k === p || k === q) continue;
        var akp = A[p][k], akq = A[q][k];
        A[p][k] = A[k][p] = c * akp - s * akq;   // 标准 NR 公式，先存旧值再更新
        A[q][k] = A[k][q] = s * akp + c * akq;
      }
      for (k = 0; k < 3; k++) {
        var vkp = V[k][p], vkq = V[k][q];
        V[k][p] = c * vkp - s * vkq;
        V[k][q] = s * vkp + c * vkq;
      }
    }
    var vals = [A[0][0], A[1][1], A[2][2]];
    var order = [0,1,2].sort(function(a,b){ return vals[b]-vals[a]; });
    var axes = [];
    for (var oi = 0; oi < 3; oi++) {
      var v = [V[0][order[oi]], V[1][order[oi]], V[2][order[oi]]];
      var L = Math.sqrt(v[0]*v[0]+v[1]*v[1]+v[2]*v[2]);
      axes.push([v[0]/L, v[1]/L, v[2]/L]);
    }
    return axes;
  }

  function centroidOf(pts, n) {
    var c = [0,0,0];
    for (var i = 0; i < n; i++) { c[0]+=pts[3*i]; c[1]+=pts[3*i+1]; c[2]+=pts[3*i+2]; }
    return [c[0]/n, c[1]/n, c[2]/n];
  }

  SEL.project = function (r, p) {
    var cam = r.getActiveCamera();
    var pos = cam.getPosition(), fp = cam.getFocalPoint(), vu = cam.getViewUp();
    var va = (cam.getViewAngle() || 30) * Math.PI / 180;
    var par = cam.getParallelProjection && cam.getParallelProjection();
    var dx = fp[0]-pos[0], dy = fp[1]-pos[1], dz = fp[2]-pos[2];
    var dl = Math.sqrt(dx*dx+dy*dy+dz*dz); dx/=dl; dy/=dl; dz/=dl;
    var rx = dy*vu[2]-dz*vu[1], ry = dz*vu[0]-dx*vu[2], rz = dx*vu[1]-dy*vu[0];
    var rl = Math.sqrt(rx*rx+ry*ry+rz*rz); rx/=rl; ry/=rl; rz/=rl;
    var ux = ry*dz-rz*dy, uy = rz*dx-rx*dz, uz = rx*dy-ry*dx;
    var vx = p[0]-pos[0], vy = p[1]-pos[1], vz = p[2]-pos[2];
    var vd = vx*dx+vy*dy+vz*dz;
    if (vd <= 0.1) return null;
    var px = vx*rx+vy*ry+vz*rz, py = vx*ux+vy*uy+vz*uz;
    var W = window.innerWidth, H = window.innerHeight;
    var vp = r.getViewport();
    var vw = vp[2]-vp[0], vh = vp[3]-vp[1];
    var aspect = (vw*W)/(vh*H);
    var ndx, ndy;
    if (par) {
      var ps = cam.getParallelScale ? cam.getParallelScale() : 10;
      ndx = px/(ps*aspect); ndy = py/ps;
    } else {
      var t = Math.tan(va/2);
      ndx = px/(vd*t*aspect); ndy = py/(vd*t);
    }
    var fx = vp[0] + (ndx*0.5+0.5)*vw;
    var fy = vp[1] + (ndy*0.5+0.5)*vh;
    return [fx*W, (1-fy)*H];
  };

  function inPoly(x, y, poly) {
    var inside = false;
    for (var i = 0, j = poly.length-1; i < poly.length; j = i++) {
      var xi = poly[i][0], yi = poly[i][1], xj = poly[j][0], yj = poly[j][1];
      if (((yi > y) !== (yj > y)) && (x < (xj-xi)*(y-yi)/(yj-yi)+xi)) inside = !inside;
    }
    return inside;
  }

  function initScene() {
    var rs = global.renderWindow.getRenderers();
    var anaR = null, plots = {};
    for (var i = 0; i < rs.length; i++) {
      var vp = rs[i].getViewport();
      var w = vp[2]-vp[0], h = vp[3]-vp[1];
      if (w > 0.3 && w < 0.4 && h > 0.9) {
        if (vp[0] > 0.6) anaR = rs[i];          // 解剖视图必须先判（避免被曲面分支拦截）
        else if (vp[0] < 0.1) plots[0] = rs[i];
        else if (vp[0] > 0.3 && vp[0] < 0.4) plots[1] = rs[i];
      }
    }
    if (!anaR || !plots[0] || !plots[1]) return false;

    var flats = [], patches = [];
    var as = anaR.getActors();
    for (i = 0; i < as.length; i++) {
      var pd = null;
      try { pd = as[i].getMapper().getInputData(); } catch (e) {}
      if (!pd) continue;
      var po = pd.getPoints();
      if (!po) continue;
      var n = po.getNumberOfPoints();
      var raw = po.getData();
      if (n === 3025) {            // 重采样平面网格 (55x55)
        var arr = new Float64Array(n*3);
        for (var k = 0; k < n*3; k++) arr[k] = raw[k];
        flats.push(arr);
      } else if (n > 7000 && n < 9000) {  // 关节窝补丁
        var arr2 = new Float64Array(n*3);
        for (k = 0; k < n*3; k++) arr2[k] = raw[k];
        patches.push(arr2);
      }
    }
    if (flats.length < 2 || patches.length < 2) return false;

    // PCA frame + uv for each flat plane
    flats = flats.map(function (pts) {
      var n = pts.length/3;
      var c = centroidOf(pts, n);
      var cov = [[0,0,0],[0,0,0],[0,0,0]];
      for (var k = 0; k < n; k++) {
        var d = [pts[3*k]-c[0], pts[3*k+1]-c[1], pts[3*k+2]-c[2]];
        for (var a = 0; a < 3; a++) for (var b = 0; b < 3; b++) cov[a][b] += d[a]*d[b]/n;
      }
      var ax = jacobi3(cov);
      var uv = new Float64Array(n*2), umin=1e9, umax=-1e9, vmin=1e9, vmax=-1e9;
      for (k = 0; k < n; k++) {
        d = [pts[3*k]-c[0], pts[3*k+1]-c[1], pts[3*k+2]-c[2]];
        var u = d[0]*ax[0][0]+d[1]*ax[0][1]+d[2]*ax[0][2];
        var v = d[0]*ax[1][0]+d[1]*ax[1][1]+d[2]*ax[1][2];
        uv[2*k] = u; uv[2*k+1] = v;
        if (u<umin)umin=u; if (u>umax)umax=u; if (v<vmin)vmin=v; if (v>vmax)vmax=v;
      }
      return { pts: pts, c: c, gx: ax[0], gy: ax[1], uv: uv, su: (umax-umin)/54, sv: (vmax-vmin)/54, cen: c };
    });

    // plot surface actors (3025 pts, z varies)
    var surf = [null, null];
    [0,1].forEach(function (pi) {
      var as2 = plots[pi].getActors();
      for (var k = 0; k < as2.length; k++) {
        var pd = null;
        try { pd = as2[k].getMapper().getInputData(); } catch (e) {}
        if (!pd) continue;
        var po = pd.getPoints();
        if (!po || po.getNumberOfPoints() !== 3025) continue;
        var raw = po.getData();
        var arr = new Float64Array(3025*3);
        var zmin=1e9, zmax=-1e9, xmin=1e9, xmax=-1e9, ymin=1e9, ymax=-1e9;
        for (var j = 0; j < 3025; j++) {
          arr[3*j] = raw[3*j]; arr[3*j+1] = raw[3*j+1]; arr[3*j+2] = raw[3*j+2];
          if (raw[3*j+2]<zmin)zmin=raw[3*j+2]; if (raw[3*j+2]>zmax)zmax=raw[3*j+2];
          if (raw[3*j]<xmin)xmin=raw[3*j]; if (raw[3*j]>xmax)xmax=raw[3*j];
          if (raw[3*j+1]<ymin)ymin=raw[3*j+1]; if (raw[3*j+1]>ymax)ymax=raw[3*j+1];
        }
        if (zmax-zmin > 0.5) surf[pi] = { pts: arr, sx: (xmax-xmin)/54, sy: (ymax-ymin)/54 };
      }
    });
    if (!surf[0] || !surf[1]) return false;

    // pair flat -> plot by grid spacing（平面与曲面的网格间距自动配对 R/L）
    flats.forEach(function (f) {
      var bpi = 0, bd = 1e9;
      [0,1].forEach(function (pi) {
        var d = Math.abs(f.su-surf[pi].sx) + Math.abs(f.sv-surf[pi].sy);
        if (d < bd) { bd = d; bpi = pi; }
      });
      f.plotR = plots[bpi];
      f.surfPts = surf[bpi].pts;
    });

    // pair patch -> flat by centroid proximity
    patches = patches.map(function (pts) {
      var n = pts.length/3;
      var c = centroidOf(pts, n);
      var bf = null, bd = 1e9;
      flats.forEach(function (f) {
        var d = Math.sqrt(Math.pow(c[0]-f.cen[0],2)+Math.pow(c[1]-f.cen[1],2)+Math.pow(c[2]-f.cen[2],2));
        if (d < bd) { bd = d; bf = f; }
      });
      return { pts: pts, n: n, cen: c, flat: bf };
    });

    SEL.anaR = anaR;
    SEL.patches = patches;
    return true;
  }

  SEL.compute = function (poly) {
    if (!SEL.ready || poly.length < 3) return;
    var results = [];
    SEL.patches.forEach(function (pch) {
      var f = pch.flat;
      var hit = [], n = pch.n;
      var stride = n > 4000 ? 2 : 1;
      for (var k = 0; k < n; k += stride) {
        var p = [pch.pts[3*k], pch.pts[3*k+1], pch.pts[3*k+2]];
        var s = SEL.project(SEL.anaR, p);
        if (s && inPoly(s[0], s[1], poly)) hit.push([p[0], p[1], p[2]]);
      }
      if (!hit.length) return;
      // map to plot grid via nearest flat-grid vertex in (u,v)
      var m = f.uv.length/2;
      var picked = {}, pts = [];
      var step = hit.length > 1200 ? Math.ceil(hit.length/1200) : 1;
      for (var h = 0; h < hit.length; h += step) {
        var dx = hit[h][0]-f.c[0], dy = hit[h][1]-f.c[1], dz = hit[h][2]-f.c[2];
        var u = dx*f.gx[0]+dy*f.gx[1]+dz*f.gx[2];
        var v = dx*f.gy[0]+dy*f.gy[1]+dz*f.gy[2];
        var bi = -1, bd = 1e9;
        for (var g = 0; g < m; g++) {
          var du = u-f.uv[2*g], dv = v-f.uv[2*g+1];
          var dd = du*du+dv*dv;
          if (dd < bd) { bd = dd; bi = g; }
        }
        if (bi >= 0 && !picked[bi]) {
          picked[bi] = 1;
          pts.push([f.surfPts[3*bi], f.surfPts[3*bi+1], f.surfPts[3*bi+2]]);
        }
      }
      if (pts.length) results.push({ plotR: f.plotR, pts: pts, anaPts: hit });
    });
    SEL.sel = results;
    var tot = 0; results.forEach(function (r) { tot += r.pts.length; });
    SEL.toast(tot > 0 ? ('已圈选 ' + tot + ' 个网格点，已在对应曲面高亮') : '未圈选到关节窝曲面区域');
  };

  SEL._test = function (cx, cy, r) {
    var poly = [];
    for (var a = 0; a < 24; a++) {
      var t = a/24*2*Math.PI;
      poly.push([cx + r*Math.cos(t), cy + r*Math.sin(t)]);
    }
    SEL.poly = poly; SEL.drawPoly();
    SEL.compute(poly);
  };

  SEL.toast = function (txt) {
    var el = document.getElementById('wb-sel-msg');
    if (!el) return;
    el.textContent = txt;
    el.style.display = 'block';
    clearTimeout(SEL.msgT);
    SEL.msgT = setTimeout(function () { el.style.display = 'none'; }, 2600);
  };

  SEL.drawPoly = function () {
    var svg = document.getElementById('wb-sel-svg');
    if (!svg) return;
    var pg = document.getElementById('wb-sel-poly');
    if (!SEL.poly.length) { pg.setAttribute('points', ''); return; }
    pg.setAttribute('points', SEL.poly.map(function (p) { return p[0]+','+p[1]; }).join(' '));
  };

  SEL.clear = function () {
    SEL.sel = []; SEL.poly = []; SEL.drawPoly();
    var cv = document.getElementById('wb-sel-cv');
    if (cv) cv.getContext('2d').clearRect(0,0,cv.width,cv.height);
  };

  SEL.toggle = function () {
    SEL.on = !SEL.on;
    var cap = document.getElementById('wb-sel-cap');
    var btn = document.getElementById('wb-sel-btn');
    var hint = document.getElementById('wb-sel-hint');
    if (SEL.on) {
      SEL.layoutCap();
      cap.style.display = 'block';
      btn.textContent = '退出圈选';
      btn.style.background = '#e67e22'; btn.style.color = '#fff';
      hint.style.display = 'block';
    } else {
      cap.style.display = 'none';
      btn.textContent = '◉ 圈选';
      btn.style.background = ''; btn.style.color = '';
      hint.style.display = 'none';
      SEL.clear();
    }
  };

  SEL.layoutCap = function () {
    var cap = document.getElementById('wb-sel-cap');
    if (!cap || !SEL.anaR) return;
    var W = window.innerWidth, H = window.innerHeight;
    var vp = SEL.anaR.getViewport();
    cap.style.left = (vp[0]*W) + 'px';
    cap.style.top = ((1-vp[3])*H) + 'px';
    cap.style.width = ((vp[2]-vp[0])*W) + 'px';
    cap.style.height = ((vp[3]-vp[1])*H) + 'px';
  };

  function tick() {
    requestAnimationFrame(tick);
    var cv = document.getElementById('wb-sel-cv');
    if (!cv) return;
    var ctx = cv.getContext('2d');
    ctx.clearRect(0, 0, cv.width, cv.height);
    if (!SEL.ready || !SEL.sel.length) return;
    var dpr = window.devicePixelRatio || 1;
    ctx.save(); ctx.scale(dpr, dpr);
    for (var g = 0; g < SEL.sel.length; g++) {
      var gr = SEL.sel[g];
      var vp = gr.plotR.getViewport();
      var W = window.innerWidth, H = window.innerHeight;
      var x0 = vp[0]*W, x1 = vp[2]*W, y0 = (1-vp[3])*H, y1 = (1-vp[1])*H;
      ctx.fillStyle = 'rgba(230,126,34,0.9)';
      for (var i = 0; i < gr.pts.length; i++) {
        var s = SEL.project(gr.plotR, gr.pts[i]);
        if (!s || s[0] < x0 || s[0] > x1 || s[1] < y0 || s[1] > y1) continue;
        ctx.beginPath(); ctx.arc(s[0], s[1], 3, 0, 6.284); ctx.fill();
      }
      ctx.fillStyle = 'rgba(211,84,0,0.75)';
      for (i = 0; i < gr.anaPts.length; i++) {
        var s2 = SEL.project(SEL.anaR, gr.anaPts[i]);
        if (!s2) continue;
        ctx.beginPath(); ctx.arc(s2[0], s2[1], 2.2, 0, 6.284); ctx.fill();
      }
    }
    ctx.restore();
  }

  function buildUI() {
    var st = document.createElement('style');
    st.textContent = '#wb-sel-btn{position:fixed;top:3%;right:1.2%;z-index:30;cursor:pointer;'
      + 'background:rgba(255,255,255,0.95);border:1px solid #999;border-radius:5px;'
      + 'padding:4px 12px;font-size:13px;font-family:"Microsoft YaHei",sans-serif;}'
      + '#wb-sel-btn:hover{background:#f0f0f0;}'
      + '#wb-sel-cap{position:fixed;display:none;z-index:25;cursor:crosshair;touch-action:none;}'
      + '#wb-sel-svg{position:fixed;inset:0;width:100%;height:100%;z-index:26;pointer-events:none;}'
      + '#wb-sel-poly{fill:rgba(230,126,34,0.15);stroke:#e67e22;stroke-width:2;stroke-dasharray:6 4;}'
      + '#wb-sel-cv{position:fixed;inset:0;width:100%;height:100%;z-index:24;pointer-events:none;}'
      + '#wb-sel-hint{position:fixed;bottom:3%;right:1.2%;z-index:30;display:none;'
      + 'background:rgba(255,255,255,0.92);border:1px solid #bbb;border-radius:5px;'
      + 'padding:4px 10px;font-size:12px;color:#555;font-family:"Microsoft YaHei",sans-serif;}'
      + '#wb-sel-msg{position:fixed;bottom:8%;left:50%;transform:translateX(-50%);z-index:31;display:none;'
      + 'background:rgba(40,40,40,0.85);color:#fff;border-radius:6px;padding:6px 14px;font-size:13px;'
      + 'font-family:"Microsoft YaHei",sans-serif;}';
    document.head.appendChild(st);

    var btn = document.createElement('button');
    btn.id = 'wb-sel-btn'; btn.textContent = '◉ 圈选';
    btn.onclick = function () { SEL.toggle(); };
    document.documentElement.appendChild(btn);

    var cap = document.createElement('div');
    cap.id = 'wb-sel-cap';
    cap.addEventListener('pointerdown', function (e) {
      if (!SEL.ready) return;
      SEL.drawing = true; SEL.poly = [[e.pageX, e.pageY]];
      try { cap.setPointerCapture(e.pointerId); } catch (err) {}
      e.preventDefault();
    });
    cap.addEventListener('pointermove', function (e) {
      if (!SEL.drawing) return;
      SEL.poly.push([e.pageX, e.pageY]); SEL.drawPoly();
    });
    cap.addEventListener('pointerup', function (e) {
      if (!SEL.drawing) return;
      SEL.drawing = false;
      SEL.poly.push([e.pageX, e.pageY]);
      SEL.drawPoly();
      SEL.compute(SEL.poly);
    });
    document.documentElement.appendChild(cap);

    var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.id = 'wb-sel-svg';
    svg.innerHTML = '<polygon id="wb-sel-poly" points=""/>';
    document.documentElement.appendChild(svg);

    var cv = document.createElement('canvas');
    cv.id = 'wb-sel-cv';
    document.documentElement.appendChild(cv);
    function sizeCv() {
      var dpr = window.devicePixelRatio || 1;
      cv.width = window.innerWidth*dpr; cv.height = window.innerHeight*dpr;
      cv.style.width = window.innerWidth+'px'; cv.style.height = window.innerHeight+'px';
    }
    sizeCv();
    window.addEventListener('resize', function () { sizeCv(); SEL.layoutCap(); });

    var hint = document.createElement('div');
    hint.id = 'wb-sel-hint';
    hint.textContent = '在右侧关节窝曲面上按住拖动圈选区域';
    document.documentElement.appendChild(hint);

    var msg = document.createElement('div');
    msg.id = 'wb-sel-msg';
    document.documentElement.appendChild(msg);

    requestAnimationFrame(tick);
  }

  function start() {
    if (!window.global || !global.renderWindow) { setTimeout(start, 200); return; }
    if (!initScene()) {
      if (!SEL.failed) { SEL.failed = true; setTimeout(function(){ SEL.failed=false; start(); }, 400); }
      return;
    }
    buildUI();
    SEL.ready = true;
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
