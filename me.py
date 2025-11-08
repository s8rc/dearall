#!/usr/bin/env python3
import sys
import os
import requests
import zipfile  # Added for zipping
import shutil   # Added for deleting the folder
import argparse # Added for handling -z and -zd flags
from requests_toolbelt.multipart.encoder import MultipartEncoder, MultipartEncoderMonitor
from tqdm import tqdm  # For the progress bar

# --- YOUR ACCOUNT DETAILS ---
# Token from your browser's local storage
TOKEN = "YKb1gKOqDJ2TWbfTggRJPU1y31Pi36H9" 

# The specific folder ID you want to upload to (the UUID)
FOLDER_ID = "dabd7396-7d74-4072-bf83-3bb3ac30a28d" 
# ----------------------------


def zip_folder(folder_path):
    """
    Zips an entire folder and returns the path to the new zip file.
    The zip file is created in the parent directory.
    """
    # Get the absolute path to ensure correct parent/basename
    abs_folder_path = os.path.abspath(folder_path)
    parent_dir = os.path.dirname(abs_folder_path)
    folder_name = os.path.basename(abs_folder_path)
    
    # Define the path for the output zip file
    zip_path = os.path.join(parent_dir, f"{folder_name}.zip")
    
    print(f"Zipping folder '{abs_folder_path}' to '{zip_path}'...")

    try:
        # Create a new zip file
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Walk the directory tree
            for root, dirs, files in os.walk(abs_folder_path):
                for file in files:
                    # Create the full path to the file
                    file_path = os.path.join(root, file)
                    
                    # Create the relative path for the file inside the zip
                    # This prevents the zip from containing the full C:\... path
                    archive_name = os.path.relpath(file_path, abs_folder_path)
                    
                    # Write the file to the zip
                    zipf.write(file_path, archive_name)

        print("Zipping complete.")
        return zip_path
        
    except Exception as e:
        print(f"Error while zipping: {e}", file=sys.stderr)
        sys.exit(1)


def upload_file_with_progress(filepath):
    """
    Uploads a single file to a specific GoFile.io folder with a progress bar.
    """
    # Check if the file exists
    if not os.path.isfile(filepath):
        print(f"ERROR: File not found at '{filepath}'", file=sys.stderr)
        # We return False on failure instead of exiting, so a batch upload can continue
        return False

    url = "https://upload.gofile.io/uploadfile"
    filename = os.path.basename(filepath)
    
    # Create the multipart encoder with all form fields
    encoder = MultipartEncoder(
        fields={
            'file': (filename, open(filepath, 'rb'), 'application/octet-stream'),
            'token': TOKEN,
            'folderId': FOLDER_ID
        }
    )
    
    progress_bar = tqdm(total=encoder.len, unit='B', unit_scale=True, desc=f"Uploading {filename}")
    
    try:
        monitor = MultipartEncoderMonitor(encoder, lambda m: progress_bar.update(m.bytes_read - progress_bar.n))
        headers = {'Content-Type': monitor.content_type}

        response = requests.post(url, data=monitor, headers=headers)
        
        progress_bar.close()
        response.raise_for_status()
        data = response.json()

        if data.get('status') == 'ok':
            link = data.get('data', {}).get('downloadPage')
            if link:
                print("\nUpload Complete!")
                print(link)
                return True # Success
            else:
                print("\nUpload failed! 'downloadPage' not found in response.", file=sys.stderr)
                print(data, file=sys.stderr)
                return False # Failure
        else:
            print(f"\nUpload failed! Status: {data.get('status')}", file=sys.stderr)
            print(data, file=sys.stderr)
            return False # Failure

    except requests.exceptions.RequestException as e:
        progress_bar.close()
        print(f"\nAn error occurred: {e}", file=sys.stderr)
        return False # Failure
    except Exception as e:
        progress_bar.close()
        print(f"\nAn unexpected error occurred: {e}", file=sys.stderr)
        return False # Failure


def main():
    # 1. Set up the argument parser
    parser = argparse.ArgumentParser(
        description="Upload a file or folder (as zip) to GoFile.io.",
        usage=f"python {os.path.basename(sys.argv[0])} [-z | -zd] <path>"
    )
    
    # Add the arguments
    parser.add_argument("path", help="Path to the file or folder to upload. Use '.' for the current directory.")
    parser.add_argument("-z", "--zip", action="store_true", help="Zip the folder before uploading.")
    parser.add_argument("-zd", "--zip-delete", action="store_true", help="Zip the folder, upload, and then delete the original folder.")
    
    # Handle case where no arguments are given
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)
        
    args = parser.parse_args()

    # 2. Decide what to do based on arguments
    
    # --- BEHAVIOR 1: Zip flags are used (-z or -zd) ---
    if args.zip or args.zip_delete:
        if not os.path.isdir(args.path):
            print(f"Error: -z and -zd flags can only be used with a directory. '{args.path}' is not a directory.", file=sys.stderr)
            sys.exit(1)
        
        # Zip the folder
        filepath_to_upload = zip_folder(args.path)
        
        # Upload the new zip file
        # We check for success before deleting
        upload_success = upload_file_with_progress(filepath_to_upload)
        
        # Delete original folder if -zd AND upload was successful
        if args.zip_delete:
            if upload_success:
                folder_to_delete = os.path.abspath(args.path)
                print(f"\nAttempting to delete original folder: {folder_to_delete}")
                try:
                    shutil.rmtree(folder_to_delete)
                    print("Successfully deleted original folder.")
                except Exception as e:
                    print(f"Error: Could not delete folder. {e}", file=sys.stderr)
            else:
                print("\nUpload failed. Original folder will not be deleted.", file=sys.stderr)
        
        sys.exit(0) # We are done

    # --- BEHAVIOR 2: No zip flags are used ---
    
    # Case 2a: The path is a single file
    if os.path.isfile(args.path):
        upload_file_with_progress(args.path)
    
    # Case 2b: The path is a directory (e.g., ".")
    elif os.path.isdir(args.path):
        print(f"Scanning directory '{os.path.abspath(args.path)}' for files...")
        files_found = 0
        script_path = os.path.abspath(sys.argv[0])

        # Get a sorted list of items for consistent upload order
        items_in_dir = sorted(os.listdir(args.path))
        
        # Iterate over all items in the directory
        for item in items_in_dir:
            full_item_path = os.path.join(args.path, item)
            
            # If it's a file, upload it
            if os.path.isfile(full_item_path):
                # Safeguard: Don't upload the script itself
                if os.path.abspath(full_item_path) == script_path:
                    print(f"Skipping script file: {item}")
                    continue
                
                files_found += 1
                print(f"\n--- Uploading file {files_found} ({item}) ---")
                upload_file_with_progress(full_item_path)
            
            # If it's a directory, skip it
            elif os.path.isdir(full_item_path):
                print(f"Skipping directory: {item}")
        
        if files_found == 0:
            print("No files found in the top-level directory to upload.")
        else:
            print(f"\n--- Batch complete: {files_found} files uploaded. ---")

    # Case 2c: The path doesn't exist
    else:
        print(f"Error: Path '{args.path}' is not a valid file or directory.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()