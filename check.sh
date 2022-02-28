'ssh bvadmin@52.158.245.71 "cat /home/bvadmin/config.toml" | diff - config.toml'
if [ $? -ne 0 ]; then
    echo "The directory was modified";
fi
