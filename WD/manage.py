#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys

# Trouver le chemin absolu du script exécutable
executable_path = os.path.abspath(sys.argv[0])
current_dir = os.path.dirname(executable_path)

print("Executable Path:", executable_path)
print("Current Directory:", current_dir)

# Chemin vers le répertoire 'WD'
parent_dir = os.path.join(current_dir, 'WD')
print("Parent Directory:", parent_dir)

# Ajouter le chemin au sys.path
sys.path.append(parent_dir)
print("Updated sys.path:", sys.path)

def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', os.path.join(current_dir, 'WD', 'settings'))
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)

if __name__ == '__main__':
    main()
