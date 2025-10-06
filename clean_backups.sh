#!/bin/bash

# Очищаем все бэкапы баз данных
find data -name "*.db.*" -type f -delete

echo "Old database backups cleaned"