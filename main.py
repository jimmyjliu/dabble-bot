import re
import os
import glob
import json
import logging
from PIL import Image
import pytesseract

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Mapping of positions to their respective projection fields
POSITION_FIELDS = {
    "RB": ["carries", "yards", "average", "td", "receptions", "receiving_yards", "receiving_td", "fantasy_points"],
    "WR": ["targets", "receptions", "receiving_yards", "average", "td", "carries", "rush_yards", "rush_td", "fantasy_points"],
    "TE": ["targets", "receptions", "receiving_yards", "average", "td", "carries", "rush_yards", "rush_td", "fantasy_points"],
    "QB": ["completions", "yards", "td", "interceptions", "carries", "rush_yards", "rush_td", "fantasy_points"],
    # Add more positions if necessary
}

ALLOWED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.gif'}

def parse_number(value):
    """
    Convert a string to an int if possible, otherwise to a float.
    Returns None if conversion fails.
    """
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return None

def clean_player_name(raw_name):
    """
    Cleans the player name by removing unwanted substrings like 'Headshot'.
    """
    return raw_name.replace("Headshot", "").strip()

def clean_team_name(raw_team):
    """
    Cleans the team name by removing concatenated strings like 'LionsLionsRB'.
    Assumes the last two characters represent the position.
    """
    if len(raw_team) > 2:
        return raw_team[:-2].strip()
    return raw_team.strip()

def parse_projections_by_position(lines, i, position):
    """
    Parse projection fields based on the player's position using POSITION_FIELDS mapping.
    Returns a dictionary of projections and the updated line index.
    """
    projections = {}
    fields = POSITION_FIELDS.get(position)
    
    if not fields:
        logger.warning(f"No projection fields defined for position: {position}")
        return projections, i

    for field in fields:
        if i >= len(lines):
            logger.error(f"Unexpected end of file while parsing projections for {position} at line {i}")
            break
        value = parse_number(lines[i].strip())
        projections[field] = value
        i += 1

    return projections, i

def parse_projections_from_file(file_path):
    """
    Parse player names and weekly projections from a single text file.
    Only lines preceded by 'Rank' and 'Player' headers are treated as player entries.
    """
    try:
        with open(file_path, "r") as file:
            lines = file.readlines()
    except FileNotFoundError:
        logger.error(f"Projections file '{file_path}' not found.")
        return []

    players = []
    i = 0
    total_lines = len(lines)

    while i < total_lines:
        line = lines[i].strip()

        if line == 'Rank' and (i + 1) < total_lines and lines[i + 1].strip() == 'Player':
            i += 2  # Move to rank line
            if i >= total_lines:
                break

            rank_line = lines[i].strip()
            if not rank_line.isdigit():
                logger.warning(f"Expected rank digit at line {i + 1}, got '{rank_line}'")
                i += 1
                continue

            rank = int(rank_line)
            i += 1  # Move to player name

            if i >= total_lines:
                break

            raw_player_name = lines[i].strip()
            player_name = clean_player_name(raw_player_name)
            i += 2  # Skip to team and position

            if i >= total_lines:
                player = {
                    "name": player_name,
                    "team": "Unknown",
                    "position": "Unknown",
                    "projections": {}
                }
                players.append(player)
                break

            raw_team_position = lines[i].strip()
            team = clean_team_name(raw_team_position)
            position = raw_team_position[-2:].strip()
            i += 1  # Move to next line

            # Advance to 'WEEK 13 PROJECTIONS'
            while i < total_lines and "WEEK 13 PROJECTIONS" not in lines[i]:
                i += 1

            if i < total_lines and "WEEK 13 PROJECTIONS" in lines[i]:
                i += 1  # Move to projections data
                projections, i = parse_projections_by_position(lines, i, position)
            else:
                projections = {}
                logger.warning(f"Projections not found for player '{player_name}' at line {i + 1}")

            player = {
                "name": player_name,
                "team": team,
                "position": position,
                "projections": projections
            }
            players.append(player)
        else:
            i += 1  # Move to next line

    logger.info(f"Total players parsed: {len(players)}")
    players_missing_projections = [p['name'] for p in players if not p.get("projections")]
    if players_missing_projections:
        logger.warning(f"Players missing projections: {players_missing_projections}")

    return players

def preprocess_image(image_path):
    """
    Preprocess the image to improve OCR accuracy by converting to grayscale and applying thresholding.
    """
    try:
        image = Image.open(image_path).convert('L')  # Convert to grayscale
        image = image.point(lambda x: 0 if x < 128 else 255, '1')  # Apply thresholding
        return image
    except Exception as e:
        logger.error(f"Error preprocessing image {image_path}: {e}")
        return None

def extract_text_from_image(image_path):
    """
    Perform OCR on an image to extract text.
    """
    try:
        image = preprocess_image(image_path)
        if image is None:
            return ""

        # Define Tesseract configuration
        custom_config = r'--oem 3 --psm 6'  # Adjust as needed

        # Perform OCR
        text = pytesseract.image_to_string(image, config=custom_config)
        logger.info(f"OCR completed for image: {image_path}")
        return text
    except Exception as e:
        logger.error(f"Error processing image {image_path}: {e}")
        return ""

def parse_line_data(extracted_text):
    """
    Parse player line data from OCR-extracted text.
    """
    lines = extracted_text.splitlines()
    combined_lines = []
    current_player = ""

    # Combine related lines
    for line in lines:
        line = line.strip()
        if not line:
            continue  # Skip empty lines
        if "(" in line and ")" in line:  # Likely a player line
            current_player = line
        elif "Receiving Yards" in line and current_player:  # Line data
            combined_lines.append(f"{current_player} {line}")
            current_player = ""  # Reset after combining

    # Parse combined lines
    player_lines = {}
    for line in combined_lines:
        # Match lines like "Amon-Ra St. Brown (WR) 70.5 Receiving Yards"
        match = re.match(r"(.+?)\s\((.+?)\)\s([\d.]+)\sReceiving Yards", line)
        if match:
            player_name = match.group(1).strip()
            position = match.group(2).strip()
            line_value = float(match.group(3).strip())
            # If player already exists, keep the highest line value
            if player_name in player_lines:
                if line_value > player_lines[player_name]["line"]:
                    player_lines[player_name] = {"position": position, "line": line_value}
            else:
                player_lines[player_name] = {"position": position, "line": line_value}
        else:
            logger.warning(f"Unmatched line format: '{line}'")

    return player_lines

def compare_projections_with_lines(projections, player_lines):
    """
    Compare projections with line data to calculate deltas and suggest bets.
    """
    results = []

    for player in projections:
        name = player.get("name", "Unknown")
        position = player.get("position", "Unknown")
        projections_data = player.get("projections", {})
        projected_yards = projections_data.get("receiving_yards")  # Adjust as needed based on position

        if name in player_lines:
            line_value = player_lines[name]["line"]

            if projected_yards is None:
                # Handle missing projection
                delta = None
                suggestion = "N/A (Missing Projections)"
            else:
                # Calculate delta and suggestion
                delta = projected_yards - line_value
                suggestion = "Over" if delta > 0 else "Under"

            results.append({
                "name": name,
                "position": position,
                "projected_yards": projected_yards if projected_yards is not None else "N/A",
                "line": line_value,
                "delta": round(delta, 2) if delta is not None else "N/A",
                "suggestion": suggestion
            })
        else:
            # Player does not have a line
            results.append({
                "name": name,
                "position": position,
                "projected_yards": projected_yards if projected_yards is not None else "N/A",
                "line": "N/A",
                "delta": "N/A",
                "suggestion": "No Line Available"
            })

    return results

def save_results_to_json(results, output_file="comparison_results.json"):
    """
    Save the comparison results to a JSON file.
    """
    with open(output_file, 'w') as json_file:
        json.dump(results, json_file, indent=4)
    logger.info(f"Results saved to {output_file}")

def main():
    """
    Main function to integrate line data with player projections and calculate deltas.
    """
    projections_file_path = "projections.txt"  # Update as needed
    images_directory = "images/"  # Update as needed

    # Parse projections from the text file
    projections = parse_projections_from_file(projections_file_path)
    if not projections:
        logger.error("No projections to process. Exiting.")
        return

    # Perform OCR on all images in the images_directory
    all_extracted_text = ""
    image_paths = glob.glob(os.path.join(images_directory, "*.*"))

    logger.info(f"Found {len(image_paths)} files in '{images_directory}' directory.")

    for image_path in image_paths:
        if not os.path.splitext(image_path)[1].lower() in ALLOWED_IMAGE_EXTENSIONS:
            logger.info(f"Skipping non-image file: {image_path}")
            continue

        extracted_text = extract_text_from_image(image_path)
        all_extracted_text += extracted_text + "\n"

    if not all_extracted_text.strip():
        logger.error("No text extracted from images. Exiting.")
        return

    # Parse aggregated line data
    player_lines = parse_line_data(all_extracted_text)
    if not player_lines:
        logger.error("No player lines parsed from images. Exiting.")
        return

    # Compare projections with line data
    comparison_results = compare_projections_with_lines(projections, player_lines)
    if not comparison_results:
        logger.error("No comparison results to display. Exiting.")
        return

    # Sort the results by absolute delta values in descending order
    sorted_results = sorted(
        comparison_results,
        key=lambda x: abs(x['delta']) if isinstance(x['delta'], (int, float)) else -float('inf'),
        reverse=True
    )

    # Display the sorted results
    logger.info("\nComparison Results (Sorted by Delta):")
    for result in sorted_results:
        logger.info(f"Player: {result['name']}")
        logger.info(f"  Position: {result['position']}")
        logger.info(f"  Projected Yards: {result['projected_yards']}")
        logger.info(f"  Line: {result['line']}")
        logger.info(f"  Delta: {result['delta']}")
        logger.info(f"  Suggestion: {result['suggestion']}")
        logger.info("-" * 30)

    # Save results to JSON
    save_results_to_json(sorted_results)

if __name__ == "__main__":
    main()
