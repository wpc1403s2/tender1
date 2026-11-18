import type { CSSProperties } from 'vue';

export interface ScreenRect extends CSSProperties {
  left: string;
  top: string;
  width: string;
  height: string;
}

/**
 * 将后端 PyMuPDF 的 BBox [x0, y0, x1, y1] 转换为前端 Canvas 覆盖层的 CSS 像素坐标
 * @param bbox 后端返回的 [x0, y0, x1, y1]
 * @param scale 当前 PDF.js 渲染的缩放比例 (viewport.scale)
 * @param padding 高亮框外扩边距 (像素)，让视觉框选更清晰
 */
export function convertPdfBboxToStyle(
  bbox: [number, number, number, number] | null,
  scale: number = 1.3,
  padding: number = 3
): ScreenRect | null {
  if (!bbox || bbox.length !== 4) return null;

  const [x0, y0, x1, y1] = bbox;
  const left = Math.max(0, x0 * scale - padding);
  const top = Math.max(0, y0 * scale - padding);
  const width = Math.max(12, (x1 - x0) * scale + padding * 2);
  const height = Math.max(12, (y1 - y0) * scale + padding * 2);

  return {
    left: `${left}px`,
    top: `${top}px`,
    width: `${width}px`,
    height: `${height}px`,
  };
}
