from pathlib import Path

# ==========================
# Configuration
# ==========================
INPUT_FILE = "Career_Advice_skills.txt"
DELIMITER = "-------------------------"   # Change this to your actual delimiter

# ==========================
# Read input file
# ==========================
with open(INPUT_FILE, "r", encoding="utf-8") as f:
    data = f.read().strip()

# ==========================
# Split into file blocks
# ==========================
blocks = data.split(DELIMITER)

for i, block in enumerate(blocks):
    block = block.strip()

    # Skip empty blocks
    if not block:
        continue

    lines = block.splitlines()

    if not lines:
        continue

    output_path = Path(lines[0].strip())

    # Remaining lines become the file contents
    file_contents = "\n".join(lines[1:]).strip()

    # Create parent directories if necessary
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write file
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(file_contents)

    print(f"Saved: {output_path}")

print("Done.")