#!/system/bin/sh
printf 'pxojdumper\nTarget: '
getprop persist.pxojdumper.package
printf '\nSet: /data/adb/modules/pxojdumper/pxojdumper set com.example.game\n'
printf 'Stop future collection: /data/adb/modules/pxojdumper/pxojdumper off\n'
printf 'Restart the target after changing it. Output: app files/pxojdumper/\n'
