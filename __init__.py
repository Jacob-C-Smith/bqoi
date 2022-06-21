import bpy
import bpy.types
from bpy.types import Operator
from struct import pack
from timeit import default_timer as timer
from bpy_extras.io_utils import ExportHelper
from bpy.props import (
    StringProperty,
    BoolProperty,
    BoolVectorProperty,
    EnumProperty,
    IntProperty,
    FloatProperty,
    CollectionProperty,   
)

bl_info = {
    "name": "Blender QOI",
    "description": "Export QOI files from the Image Editor",
    "author" : "Jacob Smith",
    "version" : (0,1),
    "blender": (3, 2, 0),
    "warning": "This software has not been rigorously tested, and may not meet commercial software completeness standards",
    "doc_url": "https://github.com/Jacob-C-Smith/bQOI/",
    "category": "Import-Export",
}


# QOI module constants
INDEX_OPERATION : int = 0
DIFF_OPERATION  : int = 64
LUMA_OPERATION  : int = 128
RUN_OPERATION   : int = 192
RGB_OPERATION   : int = 254
RGBA_OPERATION  : int = 255

MASK2           : int = 192

class QOI:
    
    colorspace      : int = None
    channels        : int = None
    width           : int = None
    height          : int = None

    def __init__(self):
        pass

    @staticmethod
    def qoi_hash(r:int, g:int, b:int, a:int):
        return (r * 3) + (g * 5) + (b * 7) + (a * 11)

    def encode(self, image: bpy.types.Image, path: str):
        
        # ┌─────────┐
        # │ Imports │
        # └─────────┘

        from struct import pack

        # ┌────────────────────┐
        # │ Uninitialized data │
        # └────────────────────┘

        run                : int  = 0

        px_len             : int  = None
        px_end             : int  = None
        px_pos             : int  = None
        px_channels        : int  = None

        f                         = None

        px                 : list = None
        previous_px        : list = None
        
        color_lookup_table : list = [ [0, 0, 0, 255] for i in range(64) ]

        pixels             : list = None

        # ┌────────────────────────┐
        # │ Prepare for file write │
        # └────────────────────────┘
        
        # Construct the image header

        # Image dimensions
        self.width      = int(image.size[0])
        self.height     = int(image.size[1])

        # Number of channels
        self.channels   = image.channels

        # sRGB or linear?
        colorspace = image.colorspace_settings.name

        if colorspace == 'sRGB':
            self.colorspace = 0
        elif colorspace == 'Linear':
            self.colorspace = 1
        else:
            raise Exception("Unknown colorspace encountered ")
            return 

        # Allocate for pixels
        px          = [ 0 for i in range(self.channels ) ] 
        previous_px = [ 0 for i in range(self.channels ) ] 

        # Useful numbers
        px_len      = self.width * self.height * self.channels
        px_end      = px_len - self.channels

        pixels      = image.pixels

        # ┌──────────────────┐
        # │ Write the header │
        # └──────────────────┘

        # Open up the file
        try:
            f = open(path,"wb",buffering=1048576) # 64 y px * 4096 x px * 4 bytes per channel
        except:
            # TODO: Throw error
            return

        # Write the magic bytes
        f.write(b"qoif")

        # Write the image dimensions
        f.write(pack(">II",self.width, self.height))

        # Write the channels and colorspace
        f.write(pack("BB",self.channels, self.colorspace))

        # ┌─────────────────┐
        # │ Write the image │
        # └─────────────────┘
        
        for px_pos in range(0, px_end, self.channels):

            #if (px_pos / self.channels) % self.width == 0:
                #print(str(int(px_pos / self.channels)))

            # Get the R, G, and B components
            r = int(pixels[px_pos + 0] * 255)
            g = int(pixels[px_pos + 1] * 255)
            b = int(pixels[px_pos + 2] * 255)
            a = 255

            # Default to opaque
            px = [r, g, b, a]

            # Overwrite the default alpha, if there is an alpha
            if self.channels == 4:
                px[3] = int(pixels[px_pos + 3]*255)


            # The current pixel is the same as the last pixel
            if px is previous_px:

                # Increment the run
                run=run+1

                # If the max run length has been reached, write the run/
                if run == 62 or px_pos == px_end:

                    # Write the run chunk
                    f.write(pack("B", (RUN_OPERATION | (run-1))))
                    run = 0

            # The current pixel is different
            else:
                i_pos = 0

                # End any run length encoding
                if run > 0:

                    # Write the run chunk
                    f.write(pack("B", (RUN_OPERATION | (run-1))))
                    run = 0

                # Make an index for the hash table
                i_pos = self.qoi_hash(r,g,b,a) % 64

                # The current pixel maps onto the color lookup table
                if color_lookup_table[i_pos] is px:

                    # Write an index chunck                    
                    f.write(pack("B",(INDEX_OPERATION|(i_pos))))

                # The current pixel doesn't map onto the color lookup table
                else:

                    # Write the current pixel to the color lookup table
                    color_lookup_table[i_pos] = px

                    # The alpha of the current and previous pixel is equal
                    if px[3]==previous_px[3]:

                        # Calculate differences from current and previous pixels
                        vr = px[0]-previous_px[0]
                        vg = px[1]-previous_px[1]
                        vb = px[2]-previous_px[2]

                        # Calculate differences of differences 
                        vg_r = vr - vg
                        vg_b = vb - vg

                        # Write a difference chunck
                        if vr > -3 and vr < 2 and vg > -3 and vg < 2 and vb > -3 and vb < 2:
                            f.write(pack("B", ( DIFF_OPERATION | (vr + 2) << 4 | (vg + 2) << 2 | (vb + 2) )))

                        # Write a luma chunk
                        elif vg_r > -9 and vg_r < 8 and vg > -33 and vg < 32 and vg_b > -9 and vg_b < 8:
                            f.write(pack("BB", ( LUMA_OPERATION | (vg + 32) ) , (( vg_r + 8 ) << 4  | vg_b + 8)))

                        # Write an RGB pixel
                        else:
                            f.write(pack("BBBB",RGB_OPERATION, px[0] ,px[1] ,px[2]))


                    # Write an RGBA
                    else:
                        f.write(pack("BBBBB",RGBA_OPERATION, px[0], px[1], px[2], px[3]))


            previous_px = px


        f.close()
        
        pass

    def write_to_file(self, path: str):

        pass

    def decode(self):

        pass

    def read_from_file(self, path: str):
        
        pass


    def __del__(self):
        pass

class qoi_io(Operator, ExportHelper):
    """
       QOI Import-Export
    """

    # TODO: Rename before shipping 1.0?
    bl_idname = "qoi_io.export"  # important since its how bpy.ops.import_test.some_data is constructed
    bl_label  = "Write QOI Image"
    
    # A few constant tuples used for EnumProperties and dropdowns
    CHANNELS    = (
        ('RGB', "RGB", "RGB"),
        ('RGBA', "RGBA", "RGBA")
    )
    
    COLORSPACE    = {
        ("sRGB", "sRGB", "Gamma corrected RGB + Linear Alpha"),
        ("Linear"  , "Linear"  , "All channels are linear")
    }
    
    # ExportHelper mixin class uses this
    filename_ext = ".qoi"
    
    # Properties used in the exporter.
    filter_glob: StringProperty(
        default = "*.qoi",
        options = {'HIDDEN'},
        maxlen  = 255,  # Max internal buffer length, longer would be clamped.
    )
    
    filepath = StringProperty(
        name        = "File Path", 
        description = "file path", 
        maxlen      =  1024,
        default     =  ""
    )

    # All the exporter tab properties
    channels_tab: EnumProperty(
        name        = "Channels tab",
        default     = "RGB",
        items       = CHANNELS,
        description = "RGB or RGBA"
    )

    # All the exporter tab properties
    colorspace_tab: EnumProperty(
        name        = "Colorspace tab",
        default     = "sRGB",
        items       = COLORSPACE,
        description = "sRGB or Linear"
    )

    # Execute 
    def execute(self, context):

        q = QOI()

        # Iterate over each area on the screen
        for a in bpy.context.screen.areas:

            # Find the image editor area
            if a.type == 'IMAGE_EDITOR':

                # Find the image editor space
                if a.spaces:
                    if a.spaces[0]:

                        # Find the image in the image editor
                        if a.spaces[0].image:
                            q.encode(image=a.spaces[0].image, path=self.filepath)
                            return {'FINISHED'}

                        # No image
                        else:
                            self.report({"ERROR"}, "There is no image in the image editor")
                            return {'CANCELLED'}
                            
                    # No image editor space
                    else:
                        self.report({"ERROR"}, "Unknown error")
                        return {'CANCELLED'}

                # No image editor space
                else:
                    self.report({"ERROR"}, "Unknown error")
                    return {'CANCELLED'}

        # No image editor on the screen
        self.report({"ERROR_INVALID_CONTEXT"}, "Please open the image editor")
        return {'CANCELLED'}
           
    # Draw everything
    def draw(self, context):
        layout = self.layout

        # Make a box for the texture options
        box    = layout.box()
        
        # Make a label for the box
        box.label(text="Texture Options", icon='TEXTURE_DATA') 
        
        # Colorspace label logic
        row = box.row()
        if self.colorspace_tab == 'sRGB':
            row.label(text="Colorspace", icon='IPO_CIRC')
        if self.colorspace_tab == 'Linear':
            row.label(text="Colorspace", icon='IPO_LINEAR')
        
        # Colorspace options
        row = box.row()
        row.prop(self, "colorspace_tab",expand=True)

        # Channel label logic
        row = box.row()        
        if self.channels_tab == 'RGB':
            row.label(text="Channels", icon='IMAGE_RGB')
        if self.channels_tab == 'RGBA':
            row.label(text="Channels", icon='IMAGE_RGB_ALPHA')
        
        # Channel options
        row = box.row()
        row.prop(self, "channels_tab",expand=True)

        return 
        
# Only needed if you want to add into a dynamic menu
def menu_func_export(self, context):
    self.layout.operator(qoi_io.bl_idname, text="Quite OK Image (.qoi)")

def register():
    bpy.utils.register_class(qoi_io)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

def unregister():
    bpy.utils.unregister_class(qoi_io)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    
# TODO: Remove before shipping version 1.0
if __name__ == "__main__":
    register()    