// Probe: measure 3D map geometry fill inside the WebGL canvas.
// Paste into browser_console (returns a Promise → result shown by the console tool).
// Target: fillW/fillH ~87-90% both axes; inside=true; top edge touching 0 = too close.
(() => {
  const c = [...document.querySelectorAll('canvas')].find((c) => {
    try { return !!(c.getContext('webgl2') || c.getContext('webgl')); } catch (e) { return false; }
  });
  if (!c) return 'NO-WEBGL-CANVAS (ECharts canvases are 2d, skip them)';
  const gl = c.getContext('webgl2') || c.getContext('webgl');
  const W = gl.drawingBufferWidth, H = gl.drawingBufferHeight;
  const buf = new Uint8Array(W * H * 4);
  return new Promise((res) => {
    // two rAFs: read after the current frame is composited (single readPixels can return all-black)
    requestAnimationFrame(() => requestAnimationFrame(() => {
      gl.readPixels(0, 0, W, H, gl.RGBA, gl.UNSIGNED_BYTE, buf);
      let minX = W, minY = H, maxX = 0, maxY = 0, n = 0;
      for (let y = 0; y < H; y += 2) {
        for (let x = 0; x < W; x += 2) {
          const i = (y * W + x) * 4;
          if (buf[i] > 20 || buf[i + 1] > 20 || buf[i + 2] > 25) {
            n++;
            if (x < minX) minX = x; if (x > maxX) maxX = x;
            if (y < minY) minY = y; if (y > maxY) maxY = y;
          }
        }
      }
      const gw = Math.ceil(W / 2), gh = Math.ceil(H / 2);
      res(JSON.stringify({
        canvas: [W, H],
        nonBgPct: (n / (gw * gh) * 100).toFixed(1),
        bbox: [minX, minY, maxX, maxY],
        fillW: ((maxX - minX) / W * 100).toFixed(1),
        fillH: ((maxY - minY) / H * 100).toFixed(1),
        inside: minX > 0 && minY > 0 && maxX < W && maxY < H,
      }));
    }));
  });
})()
