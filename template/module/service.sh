#!/system/bin/sh

if [ -z "$(getprop persist.pxojdumper.package)" ]; then
    setprop persist.pxojdumper.package "com.example.game"
fi
