pipeline {
    agent any

    environment {
    APP_DIR     = 'SustainableEventPlanning'
    VENV_DIR    = 'venv'
    DOCKER_HUB  = 'jankar-shivani08'   // your real Docker Hub username
    IMAGE_NAME  = 'sustainable-event-planner'
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

        stage('Docker Build') {
            steps {
                dir("${APP_DIR}") {
                    bat "docker build -t ${env.DOCKER_HUB}/${env.IMAGE_NAME}:${env.BUILD_NUMBER} ."
                }
            }
        }

        stage('Docker Push') {
            steps {
                script {
                    docker.withRegistry('', 'docker-hub-credentials') {
                        bat "docker push ${env.DOCKER_HUB}/${env.IMAGE_NAME}:${env.BUILD_NUMBER}"
                    }
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