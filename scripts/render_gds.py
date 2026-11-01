"""Render a GDS file to a PNG image with the ETRI layer colours (KLayout batch mode).

usage:
  klayout -b -r scripts/render_gds.py -rd gds=<in.gds> -rd png=<out.png> \
      [-rd lyp=<layer properties .lyp>] [-rd width=1600] [-rd box=x1,y1,x2,y2]

box is a window in microns (default: the whole top cell). The height follows the window's
aspect ratio. All hierarchy levels are drawn; labels and the grid are hidden.
"""
import pya

gds = globals().get('gds')
png = globals().get('png')
lyp = globals().get('lyp')
width = int(globals().get('width') or 1600)
win = globals().get('box')
if not gds or not png:
    raise RuntimeError(__doc__)

view = pya.LayoutView()
view.load_layout(gds, True)
if lyp:
    view.load_layer_props(lyp)
view.max_hier()
view.set_config('background-color', '#000000')
view.set_config('grid-visible', 'false')
view.set_config('text-visible', 'false')
if win:
    x1, y1, x2, y2 = (float(v) for v in win.split(','))
    target = pya.DBox(x1, y1, x2, y2)
else:
    bbox = view.cellview(0).cell.dbbox()
    margin = 0.02 * max(bbox.width(), bbox.height())
    target = bbox.enlarged(margin, margin)
view.zoom_box(target)
height = max(1, int(round(width * target.height() / target.width())))
view.save_image_with_options(png, width, height, 0, 2, 0, target, False)
print(f'wrote {png} ({width} x {height} px, {target.width():.1f} x {target.height():.1f} um) from {gds}')
