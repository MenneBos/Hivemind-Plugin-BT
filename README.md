# GPIO Plugin
Enables GPIO inputs for volume, mute, and command button. Current implementation
assumes raspberry pi GPIO port with physical pull up and pull down resistors.
and a mute toggle where GND == unmuted.

## Default Pin Configuration
| Pin | Connection    |
|-----|---------------|
| 22  | Volume Up     |
| 23  | Volume Down   |
| 17  | Action Button |
| 25  | Mute Switch   |





