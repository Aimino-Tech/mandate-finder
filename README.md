# mandate-finder

[![Discord](https://img.shields.io/discord/1514222622215241729?color=5865F2&label=Join%20Discord&logo=discord&logoColor=white)](https://discord.gg/GVYVCwWX)

AI-powered client mandate discovery for HR agencies. Find hiring companies, identify decision-makers, automate outreach. Powered by AGI.

## Features

- **Mandate Discovery**: Automatically find companies actively hiring
- **Decision Maker Identification**: Locate key contacts and hiring managers
- **Outreach Automation**: Generate personalized outreach messages
- **Multi-source Aggregation**: Combine data from LinkedIn, job boards, and company websites

## Installation

```bash
git clone https://github.com/Aimino-Tech/mandate-finder
cd mandate-finder
uv sync
```

## Configuration

Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
```

## Usage

```bash
# Start the API server
uvicorn src.api:app --reload

# Or run the CLI
python -m mandate_finder.cli
```

## Community

Join our [Discord community](https://discord.gg/GVYVCwWX) to ask questions, share ideas, and get help!

[![Discord Widget](https://discord.com/api/v10/guilds/1514222622215241729/widget.png?style=banner2)](https://discord.gg/GVYVCwWX)

## License

MIT
