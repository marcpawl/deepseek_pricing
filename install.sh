#!/bin/bash -ex

cd $(dirname $0)

mkdir -p ${HOME}/.config/autostart
cat<<EOF > ${HOME}/.config/autostart/deepseek_pricing.desktop
[Desktop Entry]
Type=Application
Name=DeepSeek Pricing Monitor
Comment=Tracks DeepSeek peak pricing windows
Exec=$(pwd)/deepseek_pricing.sh
Terminal=false
X-GNOME-Autostart-enabled=true
Categories=Utility;Development;
EOF

chmod +x ${HOME}/.config/autostart/deepseek_pricing.desktop
