# Project Specification: Meme Coin Meta Analysis System

## Overview

This document defines the full specification for building an intelligent system that analyzes crypto meme coins based on Telegram signals and maps them to real-world “meta” trends.

The system will run on a Pixel 5 Android device using PicoClaw, with an agent responsible for execution. The goal is to design a robust, modular, and self-improving system with clear separation of concerns.

The implementation should be production-ready, resilient, and capable of operating continuously with minimal manual intervention.

---

## Environment & Constraints

- Target device: Pixel 5 (Android)
- Runtime: PicoClaw agent environment
- LLM: GPT-4o-mini (you may suggest a better model if clearly justified)
- The system must be optimized for long-running execution on a mobile device
- Resource efficiency (CPU, memory, network) is important
- All components must be loosely coupled and modular

---

## High-Level Goal

Develop a system that analyzes crypto meme coins from Telegram channels by mapping each coin to relevant real-world “meta” trends, in order to evaluate and support buy decisions.

---

## Functional Objectives

The system must:

1. Monitor Telegram channels for newly emerging meme coins
2. Extract and structure relevant data from incoming messages
3. Identify the “meta” (trend/narrative) associated with each coin
4. Correlate coin metas with global trends (news, social, narratives)
5. Continuously adapt to evolving metas
6. Produce structured evaluations of coin potential (e.g., growth likelihood)

---

## Core Concept: Meta

A “meta” represents the underlying narrative or trend driving attention and demand.

Examples:
- War / Oil Prices → Coin: OIL
- Political Figures → Coin: 404TRUMP
- AI / Tech Trends → Coin: MYTHOS

---

## System Architecture Principles

- Strict separation of concerns between components
- Each component should be independently testable
- Avoid tight coupling between Telegram ingestion, analysis, and storage
- Design for extensibility (new data sources, new analysis layers)
- Prefer simple, maintainable solutions over complex ones

---

## Core Components

### 1. Telegram Listener (Standalone Component)

Responsibilities:
- Connect to Telegram channels
- Listen for new messages in real time
- Perform minimal preprocessing (no heavy logic)
- Forward raw or lightly structured messages to downstream components

Important:
- This component must remain isolated and simple
- It should not perform analysis or decision-making

---

### 2. Message Parser & Normalizer

Responsibilities:
- Parse incoming Telegram messages
- Extract structured fields such as:
    - Coin name / symbol
    - Market cap
    - Liquidity
    - Volume
    - Wallet activity
    - Event type (entry, whale buy, accumulation, summary, etc.)
- Normalize different message formats into a unified schema

---

### 3. Meta Analysis Engine

Responsibilities:
- Assign one or more metas to each coin
- Use:
    - Coin name
    - Context from messages
    - Historical data
- Handle ambiguity and uncertainty gracefully
- Support multiple metas per coin if needed

---

### 4. Global Trend Collector

Responsibilities:
- Continuously gather global trends from:
    - News
    - Social media
    - Emerging narratives
  - Maintain an up-to-date store of active trends
- Refresh data regularly (e.g., daily)

---

### 5. Meta Mapping System

Responsibilities:
- Correlate coin metas with global trends
- Maintain a dynamic “meta map” (graph-like structure)
- Track relationships between:
    - Coins
    - Metas
    - Trends

---

### 6. Meta Discovery & Self-Learning Loop

Responsibilities:
- Derive metas directly from:
    - Coin names
    - Descriptions
    - Behavioral patterns
- Compare derived metas with known metas
- If a meta does not exist:
    - Create a new meta
    - Track it as an emerging trend
- Continuously refine meta classification over time

---

### 7. Adaptation & Monitoring Layer

Responsibilities:
- Detect emerging metas early
- Track meta strength over time
- Identify shifts in narrative trends
- Monitor performance of past predictions

---

### 8. Evaluation Engine

Responsibilities:
- Generate structured assessments for each coin
- Consider:
    - Meta strength
    - Trend alignment
    - Whale activity
    - Momentum signals
- Output should be consistent and machine-readable

---

### 9. Feedback System (Local Web Admin)

Responsibilities:
- Provide a simple web interface running on the device
- Allow manual feedback:
    - Correct meta classifications
    - Adjust interpretations
- Feed corrections back into the system for learning

---

## Data Sources (Telegram Channels)

### Whale Trending 🐳💵

Focus:
- Whale buy activity
- Accumulation patterns
- Performance summaries

#### Example Messages

1. sends a message when whales buy a coin  
   example:  
   🔥 ‎MeowDonald's New Whale Buy!  
   🔗 X•WEB•CHART  
   🕒 Age: 2m | Security: 🚨

   🐳 Wallet: 95 SOL  
   💸 2.04 SOL → 0.09% ‎$MEOWDONALD

   💰 MC: $452,198 • 🔝 $623.1K  
   💧 Liq: $81.3K  
   📈 Vol: $326K [1h]  
   👥 Hodls: 1210

   🎯 First 20: 86% | 13 🐟 • 86%  
   🍤🍤🍤🐟🐟🐟🐟🐟🐟🐟  
   🐟🐟🐟🐟🐟🍤🐟🍤🍤🍤  
   🛠️ Dev: 0 SOL | 0% ‎$MEOWDONALD  
   ┣ Bundled: 0% 🤍  
   ┣ Airdrops: 0% 🤍  
   ┗ Made: 8 | Bond: 2 | Best: $668.2K

2. another whale bought  
   🌊🐳 Another Whale Aped ‎$MEOWDONALD!  
   🔗 X•WEB•CHART

🐳 Wallet: 238 SOL  
💸 2.7 SOL → 0.13% ‎$MEOWDONALD

💰 MC: $428,395 • 🔝 $791K  
📈 Vol: $439.6K [1h]  
👥 Hodls: 1537

3. Whale accumulated  
   ➕🐳 Whale Accumulating ‎$MEOWDONALD!  
   🔗 X•WEB•CHART

🐳 Wallet: 238 SOL  
💸 4.03 SOL → 0.68% ‎$MEOWDONALD

💰 MC: $123,871 • 🔝 $712.2K  
📈 Vol: $2.2M [1h]  
👥 Hodls: 1494

4. Percentage gain message since entry of the first whale  
   📈 ‎LIQUID is up 51% 📈  
   from ⚡️ Entry Signal

   $164K —> $248.3K 💵  
   💸💸

5. Summary messages  
   🥇 ‎Emulites | EMULITES | 3K%  
   🥈 ‎Gloat | GLOAT | 203%  
   🥉 ‎LAD | LAD | 366%

dark money | DUSD | 207%  
Bonk Index | BNKK | 1.4K%  
Le Lamp | LeLamp | 34%  
Hive Mind | HIVEMIND | -65%  
チコリータ | Chikorita | -7%  
|  | 577%  
Solana Shades | Shades | 283%  
SCP-067 | 067 | 39%  
Time | Time | 34%

---

### Solana Early Trending 💵

Focus:
- Early signals
- Volatility
- Entry opportunities

#### Example Messages

1. Entry signal

🔥 ‎Doom Neuron New Trending  
🕒 Age: 10m | Security: ⚠️  
🔗 X•WEB•CHART

	💰 MC: $24,440 • 🔝 $61.9K  
	💧 Liq: $12.1K  
	📈 Vol: 1h: $109K  
	┗   Fake: $831 [0.8%]  
	👥 Hodls: 233  

	📦 /Bundles: 31 • 111% → 17.8%  
	🔫 Snipers: 3 • 1% → 0% 🤍  
	🎯 First 20: 26% | 12 📦 • 16%  
	🛠📦📦📦📦📦📦📦📦📦  
	📦📦📦🐟🐟🍤🐟🐟🐟🍤  

	🛠️ Dev: 32 SOL | 0% $DOOM  
	┣ Bundled: 23% ⚠️ | Sold: 23% 🔴  
	┗ Made: 10 | Bond: 2 | Best: $62.8K  

2. Percentage gain message since entry message

📈 ‎DOOM is up 59% 📈  
from ⚡️ Entry Signal

$24.4K —> $39K 💵  
💸💸

3. Summary message

🏆 Top Early Trending 💸

🥇 ‎Brent Crude | $‎BRENT • ‎200X [TG]

🥈 ‎World Rebuilding Trust | $‎WRT • ‎100X [X]

🥉 ‎Just A Socks | $‎SOCKS • ‎60X [X]

4⃣ $‎BABYTRUMP • ‎15X  
5⃣ $‎TIGER • ‎7X  
6⃣ $‎BELIEVE • ‎10X [TG]  
7⃣ $‎STONKS • ‎26X  
8⃣ $‎TRADE • ‎1X  
$‎IROHA • ‎5X  
$‎PWAH • ‎5X  
$‎MIMI • ‎10X  
$‎UE • ‎40X [TG]

---

## Configuration

Create a `.configuration` file that includes all required environment variables.

Examples of what should be configurable:
- Telegram access credentials
- Channel identifiers
- API keys for external data sources
- LLM configuration
- Storage configuration
- Logging levels

Do not hardcode sensitive values.

---

## Non-Functional Requirements

- System must be resilient to malformed or unexpected messages
- Must support continuous operation
- Should log key events and decisions
- Must handle partial failures gracefully
- Should be easy to extend with new data sources or analysis layers

---

## Expected Output

The system should produce structured outputs that include:
- Coin identification
- Extracted metrics
- Assigned metas
- Meta strength / confidence
- Trend alignment
- Evaluation summary

---

## Notes for Implementation

- Avoid overengineering
- Prefer clarity over complexity
- Make reasonable assumptions where ambiguity exists
- Only ask questions if absolutely necessary for correctness
- Ensure the system is maintainable and debuggable

---