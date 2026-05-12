#include <clocale>
#include <iostream>
#include <fstream>
#include <string>

int main () {
    setlocale(LC_ALL, "RU");
    
    std::string SearchedPassword;
    std::cout << "Введите пароль для поиска: ";
    std::cin >> SearchedPassword;
    std::ifstream file("passwords.txt");
    bool found = false;

        if (file) {
            std::string line;
            while (getline(file, line))
            if (line == SearchedPassword) {
                std::cout << "Пароль найден: [" << SearchedPassword << "] и [" << line << "]" << std::endl;
                found = true;
                break;
            }
        
        
             if (!found) {
                 std::cout << "Ошибка, пароль не найден!" << std::endl;
            }

        else {
            std::cout << "Ошибка, фаил не открывается!" << std::endl;
        }
    

    return 0;
}
