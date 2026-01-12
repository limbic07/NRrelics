# NRrelic_Bot

An automated relic screening assistant based on OCR and simulated input. Designed to save your time and fingers. Based on OCR, so it only support NR in Simplified Chinese version.

## ⚠️ Disclaimer (Must Read)

This software operates solely on **Optical Character Recognition (OCR)** and **simulated mouse/keyboard clicks**. It **does not** read or modify any game memory.

* **Safety**: While theoretically safe, using automation scripts in online environments always carries risk.
* **Recommendation**: **Strongly recommended for use in Offline Mode or with EAC (Easy Anti-Cheat) disabled.**
* **Liability**: This tool is for educational purposes only. The author is not responsible for any bans resulting from online use.
* **Fair Play**: Not intended for malicious Save-Load (SL) exploits.

## ✨ Features

* **Auto-Recognition**: Automatically identifies relic attributes using OCR.
* **Dual Modes**: Supports both "Normal" and "Deepnight" relic modes.
* **Smart Filtering**:
    * **Custom Presets**: Define multiple desired attribute combinations (e.g., "Phys Atk + HP" for melee, "Magic Atk + Crit" for mages).
    * **Logic**: If a relic matches 2 or more attributes from *any* active preset, it is **kept**. Otherwise, it is automatically **sold**.
* **Blacklist System**: Automatically detects and sells relics with "fatal" negative attributes (e.g., "HP Drain") defined in your blacklist.

## 📖 How to Use

1.  **Launch**:
    * Open the game and stand in front of the **Pot Merchant** or the **Collector** interface.
    * Run `NRrelic_Bot.exe`.
2.  **Configure**:
    * Select your mode (Normal/Deepnight).
    * Add your desired attribute presets in the software.
3.  **Start AFK**:
    * In the game, aim your crosshair/cursor at the item you want to purchase.
    * Click the **Start** button on the bot.
    * The bot will automatically loop: `Buy -> Scan -> Keep/Sell`.

### ⌨️ Key Mappings
The software uses the default game keybinds:
* **Interact (Buy/Confirm)**: `F`
* **Sell**: `3`
* **Stop/Pause Bot**: `F11`

---

## 🤝 Acknowledgments

* **Data Source**: The relic attribute list used in this project is referenced from the guide by Bilibili content creator **Cinderella小辛**.
