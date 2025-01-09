import os
import boto3
import folder_paths
from dotenv import load_dotenv
from .utils import unescape_env_value

print("[EmProps] S3VideoCombine: Starting imports")
try:
    print("[EmProps] S3VideoCombine: Importing VHS nodes module")
    import importlib
    from .deps.VHS_VideoHelperSuite.videohelpersuite import nodes as vhs_nodes
    # Force reload the module to ensure initialization runs
    importlib.reload(vhs_nodes)
    print("[EmProps] S3VideoCombine: VHS nodes imported successfully")
    print(f"[EmProps] S3VideoCombine: VHS module path: {vhs_nodes.__file__}")
    print(f"[EmProps] S3VideoCombine: Available formats right after import: {folder_paths.get_filename_list('VHS_video_formats')}")
except Exception as e:
    print(f"[EmProps] S3VideoCombine: Error importing VHS nodes: {str(e)}")
    raise

class EmProps_S3_Video_Combine(vhs_nodes.VideoCombine):
    """
    Node for combining videos and uploading to S3 with dynamic prefix support
    """
    def __init__(self):
        super().__init__()
        self.s3_bucket = "emprops-share"
        self.type = "s3_video_output"
        self.output_dir = folder_paths.get_output_directory()
        
        # First try system environment
        self.aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
        self.aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        self.aws_region = os.getenv('AWS_DEFAULT_REGION')

        # If not found, try .env and .env.local files
        if not self.aws_access_key or not self.aws_secret_key:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            
            # Try .env first
            env_path = os.path.join(current_dir, '.env')
            if os.path.exists(env_path):
                print("[EmProps] Loading .env from: " + env_path)
                load_dotenv(env_path)
                self.aws_secret_key = self.aws_secret_key or unescape_env_value(os.getenv('AWS_SECRET_ACCESS_KEY_ENCODED', ''))
                if not self.aws_secret_key:
                    self.aws_secret_key = self.aws_secret_key or os.getenv('AWS_SECRET_ACCESS_KEY', '')
                    print("[EmProps] AWS_SECRET_ACCESS_KEY_ENCODED not found in .env, trying AWS_SECRET_ACCESS_KEY")
                self.aws_access_key = self.aws_access_key or os.getenv('AWS_ACCESS_KEY_ID', '')
                self.aws_region = self.aws_region or os.getenv('AWS_DEFAULT_REGION', '')
            
            # If still not found, try .env.local
            if not self.aws_access_key or not self.aws_secret_key:
                env_local_path = os.path.join(current_dir, '.env.local')
                if os.path.exists(env_local_path):
                    print("[EmProps] Loading .env.local from: " + env_local_path)
                    load_dotenv(env_local_path)
                    self.aws_secret_key = self.aws_secret_key or unescape_env_value(os.getenv('AWS_SECRET_ACCESS_KEY_ENCODED', ''))
                    if not self.aws_secret_key:
                        self.aws_secret_key = self.aws_secret_key or os.getenv('AWS_SECRET_ACCESS_KEY', '')
                        print("[EmProps] AWS_SECRET_ACCESS_KEY_ENCODED not found in .env.local, trying AWS_SECRET_ACCESS_KEY")
                    self.aws_access_key = self.aws_access_key or os.getenv('AWS_ACCESS_KEY_ID', '')
                    self.aws_region = self.aws_region or os.getenv('AWS_DEFAULT_REGION', '')

    @classmethod
    def INPUT_TYPES(cls):
        parent_types = super().INPUT_TYPES()
        parent_types["required"].update({"s3_prefix": ("STRING", {"default": "videos/"})})
        return parent_types

    RETURN_TYPES = ("STRING", "VHS_FILENAMES")
    RETURN_NAMES = ("url", "filenames")
    FUNCTION = "combine_and_upload"
    OUTPUT_NODE = True
    CATEGORY = "EmProps"

    def combine_and_upload(self, images, frame_rate, loop_count, filename_prefix, s3_prefix, format="video/h264-mp4", pingpong=False, save_output=True, audio=None, prompt=None, extra_pnginfo=None, unique_id=None, manual_format_widgets=None, meta_batch=None, vae=None, **kwargs):
        print("[EmProps] S3VideoCombine: Starting combine_and_upload")
        print(f"[EmProps] S3VideoCombine: Using format {format}")
        print(f"[EmProps] S3VideoCombine: Format type: {type(format)}")
        print(f"[EmProps] S3VideoCombine: Manual format widgets: {manual_format_widgets}")
        print(f"[EmProps] S3VideoCombine: kwargs: {kwargs}")
        
        # Get the format extension (strip off 'video/')
        format_ext = format.split('/')[-1] if '/' in format else format
        print(f"[EmProps] S3VideoCombine: Format extension: {format_ext}")
        
        # Check if format exists
        format_path = folder_paths.get_full_path("VHS_video_formats", format_ext + ".json")
        print(f"[EmProps] S3VideoCombine: Format path: {format_path}")
        print(f"[EmProps] S3VideoCombine: Available formats: {folder_paths.get_filename_list('VHS_video_formats')}")
        
        if format_path is None:
            print(f"[EmProps] S3VideoCombine: WARNING - Format not found: {format_ext}")
            print(f"[EmProps] S3VideoCombine: Current folder_paths: {folder_paths.folder_names_and_paths}")
        
        # First combine the video using parent class
        filenames = super().combine_video(
            images=images,
            frame_rate=frame_rate,
            loop_count=loop_count,
            filename_prefix=filename_prefix,
            format=format,
            pingpong=pingpong,
            save_output=save_output,
            audio=audio,
            prompt=prompt,
            extra_pnginfo=extra_pnginfo,
            unique_id=unique_id,
            manual_format_widgets=manual_format_widgets,
            meta_batch=meta_batch,
            vae=vae,
            **kwargs
        )
        video_path = filenames[0]  # Get the first filename from the VHS_FILENAMES tuple
        
        try:
            # Initialize S3 client
            s3_client = boto3.client(
                's3',
                aws_access_key_id=self.aws_access_key,
                aws_secret_access_key=self.aws_secret_key,
                region_name=self.aws_region
            )

            # Clean up the prefix
            s3_prefix = s3_prefix.strip('/')
            if s3_prefix:
                s3_prefix += '/'

            # Get the filename from the path
            filename = os.path.basename(video_path)
            
            # Upload to S3
            s3_key = f"{s3_prefix}{filename}"
            content_type = format
            
            s3_client.upload_file(
                video_path,
                self.s3_bucket,
                s3_key,
                ExtraArgs={'ContentType': content_type}
            )

            # Generate the URL
            url = f"https://{self.s3_bucket}.s3.amazonaws.com/{s3_key}"
            print(f"[EmProps] Video uploaded successfully to: {url}")
            
            return (url, filenames)
            
        except Exception as e:
            print(f"[EmProps] Error uploading to S3: {str(e)}")
            raise e
