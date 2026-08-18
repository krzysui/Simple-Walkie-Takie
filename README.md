# Simple-Walkie-Takie
Simple Walkie Takie App for Mobile Devices (after hours vibecoded project).
# 📻 Simple LAN & Server Walkie-Talkie

> Lekki, bezpieczny i ultraszybki komunikator Push-to-Talk (PTT) dla systemu Android z obsługą trybu bezserwerowego (P2P LAN) oraz dedykowanego serwera z panelem WWW.

---

## 🚀 Główne Możliwości

* **Dwa tryby pracy:**
  * **P2P (LAN Broadcast):** Całkowicie bezserwerowa komunikacja w zasięgu jednej sieci Wi-Fi.
  * **Dedykowany Serwer Relay:** Centralny serwer w Pythonie z dynamiczną listą pokoi i webowym panelem zarządzania.
* **Szyfrowanie End-to-End (E2EE):** Ochrona transmisji głosu algorytmem **AES-256** (z kluczem generowanym przez SHA-256 z hasła).
* **Niskie opóźnienia (*Low-Latency*):** Dźwięk przesyłany w czasie rzeczywistym (16 kHz, 16-bit Mono PCM) przez protokół **UDP**.
* **System Użytkowników & Uprawnień:**
  * Własne nicki lub automatyczne generowanie unikalnych `guestXXXXX`.
  * Twórca pokoju automatycznie otrzymuje rolę **Administratora (👑)** i możliwość usuwania pokoju.
  * Przewijana lista obecnych użytkowników w pokoju na żywo.
* **Panel Webowy Administratora (Dashboard WWW):** Wbudowany serwer WWW pod portem `8080` do podglądu pokoi, usuwania kanałów, wyrzucania użytkowników i przeglądu logów w czasie rzeczywistym.

---

## 🛠 Wymagania i Uruchomienie

### 1. Uruchomienie Serwera (Python 3.8+)
Serwer nie wymaga żadnych zewnętrznych bibliotek (`pip install`). Wystarczy uruchomić:
