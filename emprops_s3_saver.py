import os
import boto3
import folder_paths
from dotenv import load_dotenv
from .utils import unescape_env_value
from .helpers.image_save_helper import ImageSaveHelper

class EmProps_S3_Saver:
    """
    Node for saving files to S3 with dynamic prefix support
    """
    def __init__(self):
        self.s3_bucket = "emprops-share"
        self.image_helper = ImageSaveHelper()
        self.type = "s3_output"
        self.output_dir = folder_paths.get_output_directory()
        self.compress_level = 4
        
        # First try system environment
        self.aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
        self.aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        self.aws_region = os.getenv('AWS_DEFAULT_REGION')

        # If not found, try .env.local
        if not self.aws_access_key or not self.aws_secret_key:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            env_path = os.path.join(current_dir, '.env.local')
            if os.path.exists(env_path):
                load_dotenv(env_path)
                # Get and unescape AWS credentials from .env.local
                self.aws_secret_key = self.aws_secret_key or unescape_env_value(os.getenv('AWS_SECRET_ACCESS_KEY_ENCODED', ''))
                self.aws_access_key = self.aws_access_key or os.getenv('AWS_ACCESS_KEY_ID', '')
                self.aws_region = self.aws_region or os.getenv('AWS_DEFAULT_REGION', '')

        # Set default region if still not set
        self.aws_region = self.aws_region or 'us-east-1'

        if not self.aws_secret_key or not self.aws_access_key:
            print("[EmProps] Warning: AWS credentials not found in environment or .env.local")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "prefix": ("STRING", {"default": "uploads/"}),
                "filename": ("STRING", {"default": "image.png"}),
                "bucket": ("STRING", {"default": "emprops-share"})
            },
            "hidden": {
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO"
            }
        }

    RETURN_TYPES = ()  
    FUNCTION = "save_to_s3"
    CATEGORY = "EmProps"
    OUTPUT_NODE = True
    DESCRIPTION = "Saves the input images to S3 with configurable bucket and prefix and displays them in the UI."

    def save_to_s3(self, images, prefix, filename, bucket, prompt=None, extra_pnginfo=None):
        """Save images to S3 with the specified prefix and filename"""
        try:
            # Debug: Print credentials being used (first 4 chars only)
            if self.aws_access_key:
                print(f"[EmProps] Debug - Using Access Key ID: {self.aws_access_key[:4]}...")
            if self.aws_secret_key:
                print(f"[EmProps] Debug - Using Secret Key: {self.aws_secret_key[:4]}...")
            print(f"[EmProps] Debug - Using Region: {self.aws_region}")

            # Try using default session first
            s3_client = boto3.client('s3')
            
            # If that fails, try explicit credentials
            if self.aws_access_key and self.aws_secret_key:
                s3_client = boto3.client(
                    's3',
                    aws_access_key_id=self.aws_access_key,
                    aws_secret_access_key=self.aws_secret_key,
                    region_name=self.aws_region
                )
            
            # Ensure prefix ends with '/'
            if not prefix.endswith('/'):
                prefix += '/'
            
            # Remove leading '/' if present
            if prefix.startswith('/'):
                prefix = prefix[1:]
            
            # Process images using the helper
            processed_images = self.image_helper.process_images(images, prompt, extra_pnginfo)
            
            results = []
            for idx, (img_bytes, metadata) in enumerate(processed_images):
                # Handle multiple images by adding index to filename
                if len(processed_images) > 1:
                    base, ext = os.path.splitext(filename)
                    current_filename = f"{base}_{idx}{ext}"
                else:
                    current_filename = filename
                
                # Get full output path for local save
                full_output_folder, filename_with_path, counter, subfolder, _ = folder_paths.get_save_image_path(current_filename, self.output_dir, images[0].shape[1], images[0].shape[0])
                
                # Save locally first
                local_filename = f"{filename_with_path}_{counter:05}_.png"
                local_path = os.path.join(full_output_folder, local_filename)
                
                # Save to local file
                with open(local_path, 'wb') as f:
                    img_bytes.seek(0)
                    f.write(img_bytes.getvalue())
                
                # Construct the full S3 key
                s3_key = f"{prefix}{current_filename}"
                
                # Upload to S3
                img_bytes.seek(0)
                s3_client.upload_fileobj(img_bytes, bucket, s3_key)
                
                # Create result entry for UI
                results.append({
                    "filename": local_filename,
                    "subfolder": subfolder,
                    "type": self.type,
                    "s3_url": f"s3://{bucket}/{s3_key}"
                })
                
                print(f"[EmProps] Successfully saved {local_filename} and uploaded to s3://{bucket}/{s3_key}")
            
            # Return both UI images and S3 URLs
            return {"ui": {"images": results}}
            
        except Exception as e:
            print(f"[EmProps] Error saving to S3: {str(e)}")
            return {}
