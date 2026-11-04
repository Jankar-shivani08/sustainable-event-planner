pipeline {
    agent any

    environment {
        APP_DIR  = 'SustainableEventPlanning'
        VENV_DIR = 'venv'
    }

    stages {
        stage('Checkout') {
            steps { checkout scm }
        }

        stage('Setup Python') {
            steps {
                dir("${APP_DIR}") {
                    bat '''
                        python -m venv %VENV_DIR%
                        call %VENV_DIR%\\Scripts\\activate.bat
                        python -m pip install --upgrade pip
                        pip install -r requirements.txt
                    '''
                }
            }
        }

        stage('Django System Check') {
            steps {
                dir("${APP_DIR}") {
                    bat '''
                        call %VENV_DIR%\\Scripts\\activate.bat
                        python manage.py check
                    '''
                }
            }
        }

        stage('Run Tests') {
            steps {
                dir("${APP_DIR}") {
                    bat '''
                        call %VENV_DIR%\\Scripts\\activate.bat
                        python manage.py test
                    '''
                }
            }
        }
    }

    post {
        always {
            dir("${APP_DIR}") {
                bat 'if exist %VENV_DIR% rmdir /s /q %VENV_DIR%'
            }
        }
    }
}