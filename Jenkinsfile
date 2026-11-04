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
                    sh '''
                        python3 -m venv ${VENV_DIR}
                        . ${VENV_DIR}/bin/activate
                        pip install --upgrade pip
                        pip install -r requirements.txt
                    '''
                }
            }
        }

        stage('Django System Check') {
            steps {
                dir("${APP_DIR}") {
                    sh '''
                        . ${VENV_DIR}/bin/activate
                        python manage.py check
                    '''
                }
            }
        }

        stage('Run Tests') {
            steps {
                dir("${APP_DIR}") {
                    sh '''
                        . ${VENV_DIR}/bin/activate
                        python manage.py test
                    '''
                }
            }
        }
    }

    post {
        always {
            dir("${APP_DIR}") {
                sh 'rm -rf ${VENV_DIR} || true'
            }
        }
    }
}