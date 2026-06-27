import os

# الملف النهائي الذي سيحتوي على كل الكود
output_file = "all_project_code.txt"

# المجلدات أو الملفات التي تريد استثناءها
ignored_dirs = [".git", "__pycache__", "venv", ".env"]
ignored_files = ["merge.py", "all_project_code.txt"]

with open(output_file, "w", encoding="utf-8") as outfile:
    for root, dirs, files in os.walk("."):
        # استثناء المجلدات غير المرغوبة
        dirs[:] = [d for d in dirs if d not in ignored_dirs]
        
        for file in files:
            if file.endswith(".py") and file not in ignored_files:
                file_path = os.path.join(root, file)
                outfile.write(f"\n\n# ==========================================\n")
                outfile.write(f"# FILE: {file_path}\n")
                outfile.write(f"# ==========================================\n\n")
                
                try:
                    with open(file_path, "r", encoding="utf-8") as infile:
                        outfile.write(infile.read())
                except Exception as e:
                    outfile.write(f"# [خطأ في قراءة الملف: {e}]\n")

print(f"✅ تم دمج جميع الملفات بنجاح في ملف واحد: {output_file}")