import re
from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig

# Simple structured extraction: timestamp, level, service, message
LOG_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>[A-Z]+)\s+"
    r"\[(?P<service>[^\]]+)\]\s+"
    r"(?P<message>.+)$"
)

def create_template_miner() -> TemplateMiner:
    """Create a configured Drain3 template miner."""
    config = TemplateMinerConfig()

    # Disable profiling
    config.profiling_enabled = False

    # Lower similarity threshold: more aggressive merging
    config.drain_sim_th = 0.4

    # Maximum parse tree depth
    config.drain_depth = 4

    return TemplateMiner(config=config)



def parse_log_line(line: str, miner: TemplateMiner) -> dict | None:
    """
    Parse a single log line:
    1. Extract structured fields (timestamp, level, service, message)
    2. Run the message through Drain3 to get a template
    Returns None if the line doesn't match the expected format.
    """
    match = LOG_PATTERN.match(line.strip())
    if not match:
        return None

    structured = match.groupdict()
    message = structured["message"]

    # Feed the message (not the full line) to Drain3
    result = miner.add_log_message(message)

    # Extract parameters by comparing the template to the original message
    template = result["template_mined"]
    params = miner.extract_parameters(template, message)

    return {
        "timestamp": structured["timestamp"],
        "level": structured["level"],
        "service": structured["service"],
        "message": message,
        "template": template,
        "cluster_id": result["cluster_id"],
        "parameters": params if params else [],
        "change_type": result["change_type"],
    }


def parse_log_text(raw_text: str) -> dict:
    """
    Parse an entire block of raw log text.
    Returns structured lines, template summary, and parse statistics.
    """
    miner = create_template_miner()
    lines = raw_text.strip().split("\n")

    parsed_lines = []
    skipped = 0

    for line in lines:
        if not line.strip():
            continue
        parsed = parse_log_line(line, miner)
        if parsed:
            parsed_lines.append(parsed)
        else:
            skipped += 1

    # Build a template summary: how many times each template appeared
    template_counts = {}
    for pl in parsed_lines:
        tid = pl["cluster_id"]
        if tid not in template_counts:
            template_counts[tid] = {
                "cluster_id": tid,
                "template": pl["template"],
                "count": 0,
                "sample_service": pl["service"],
                "sample_level": pl["level"],
            }
        template_counts[tid]["count"] += 1

    return {
        "total_lines": len(lines),
        "parsed_lines": len(parsed_lines),
        "skipped_lines": skipped,
        "unique_templates": len(template_counts),
        "templates": list(template_counts.values()),
        "lines": parsed_lines,
    }