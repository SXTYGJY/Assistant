# -*- coding: utf-8 -*-

from flask import Flask, render_template, request, redirect, url_for, session, flash, Response, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector
from intent_recognition import execute as intent_execute
import json
from functools import wraps

app = Flask(__name__)
app.secret_key = 'change_this_to_a_random_string_abc123'  # 替换为实际的密钥

from config import DB_CONFIG_BUSINESS

def get_db_connection():
    """获取数据库连接"""
    conn = mysql.connector.connect(**DB_CONFIG_BUSINESS)
    return conn

# 登录装饰器
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('请先登录')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('chat'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # 简单的用户名和密码验证
        if not username or not password:
            flash('用户名和密码不能为空')
            return render_template('register.html')

        if len(password) < 6:
            flash('密码长度至少为6位')
            return render_template('register.html')

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            # 检查用户名是否已存在
            cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
            existing_user = cursor.fetchone()

            if existing_user:
                flash('用户名已存在，请选择其他用户名')
                return render_template('register.html')

            # 创建新用户
            password_hash = generate_password_hash(password)
            cursor.execute(
                "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
                (username, password_hash)
            )
            conn.commit()

            flash('注册成功，请登录')
            return redirect(url_for('login'))

        except Exception as e:
            flash(f'注册失败: {str(e)}')
            return render_template('register.html')
        finally:
            if 'cursor' in locals():
                cursor.close()
            if 'conn' in locals():
                conn.close()

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
            user = cursor.fetchone()

            if not user:
                flash('用户不存在，请联系管理员获取账户')
                return redirect(url_for('login'))

            if check_password_hash(user['password_hash'], password):
                session['user_id'] = user['id']
                session['username'] = user['username']

                # 更新最后登录时间
                cursor.execute(
                    "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s",
                    (user['id'],)
                )
                conn.commit()

                flash('登录成功')
                return redirect(url_for('chat'))
            else:
                flash('密码错误')
        except Exception as e:
            flash(f'登录失败: {str(e)}')
        finally:
            cursor.close()
            conn.close()
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('您已登出')
    return redirect(url_for('login'))

@app.route('/chat')
@login_required
def chat():
    # 获取用户对话历史数量，用于判断是否是首次访问
    is_first_visit = True
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) as count FROM user_conversations WHERE user_id = %s", (session['user_id'],))
        result = cursor.fetchone()
        is_first_visit = result['count'] == 0 if result else True
    except Exception as e:
        print(f"获取用户对话历史失败: {str(e)}")
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

    # 获取用户名首字母
    user_initials = session['username'][0].upper() if session['username'] else 'U'

    return render_template('chat.html',
                         username=session['username'],
                         is_first_visit=is_first_visit,
                         user_initials=user_initials)

@app.route('/api/chat', methods=['POST', 'GET'])
@login_required
def api_chat():
    if request.method == 'GET':
        # 处理GET请求，从URL参数获取query
        user_query = request.args.get('query', '')
    else:
        # 处理POST请求，从JSON数据获取query
        if request.content_type == 'application/json':
            json_data = request.get_json()
            user_query = json_data.get('query', '') if json_data else ''
        else:
            user_query = request.form.get('query', '')

    user_id = session['user_id']

    # 检查是否是首次进入聊天页面的请求（空查询）
    is_welcome_request = not user_query.strip()

    if is_welcome_request:
        # 返回欢迎消息
        welcome_message = """👋 欢迎使用智能数据助手  

你可以直接向我提问表、字段或指标相关的问题，例如：

- 用户每日登录事实表是做什么的？ 

- login_date 字段代表什么含义？

- 最近30天活跃用户总数的指标定义？ 

我会基于系统中的元数据，为你提供专业、准确的解答。"""

        return jsonify({
            'conversation_id': None,
            'content': welcome_message,
            'is_welcome': True
        })

    # 调用意图识别和对话系统
    try:
        response = intent_execute(user_query, user_id)
        print(user_id)
        print("=" * 40)
        print(response)
        print("=" * 40)

        # 检查是否返回了有效的响应
        if not response or response.startswith("抱歉"):
            raise ValueError("意图识别模块返回无效响应")

    except Exception as e:
        print(f"API处理错误: {str(e)}")
        response = f"系统错误: {str(e)}\n\n技术细节已记录，请联系管理员"
        return jsonify({
            'error': True,
            'content': response,
            'detail': str(e)
        }), 500

    # 保存对话历史
    conversation_id = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO user_conversations (user_id, query, response) VALUES (%s, %s, %s)",
            (session['user_id'], user_query, response)
        )
        conversation_id = cursor.lastrowid
        conn.commit()
    except Exception as e:
        print(f"保存对话历史失败: {str(e)}")
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

    # 返回完整响应（包含对话ID和内容）
    return jsonify({
        'conversation_id': conversation_id,
        'content': response,
        'is_welcome': False
    })

@app.route('/api/rate', methods=['POST'])
@login_required
def api_rate():
    """用户评价对话质量"""
    try:
        data = request.get_json()
        conversation_id = data.get('conversation_id')
        rating = data.get('rating')  # 1-5分
        liked = data.get('liked')    # true/false

        if not conversation_id:
            return jsonify({'error': '缺少对话ID'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        update_fields = ['rated_at = CURRENT_TIMESTAMP']
        params = []

        if rating is not None:
            update_fields.append('user_rating = %s')
            params.append(rating)

        if liked is not None:
            update_fields.append('user_liked = %s')
            params.append(1 if liked else 0)

        params.append(conversation_id)

        query = f"UPDATE user_conversations SET {', '.join(update_fields)} WHERE id = %s"
        cursor.execute(query, params)
        conn.commit()

        cursor.close()
        conn.close()

        return jsonify({'success': True, 'message': '评价成功'})

    except Exception as e:
        print(f"评价保存失败: {str(e)}")
        return jsonify({'error': '评价失败'}), 500

@app.route('/admin')
@login_required
def admin():
    """后台管理页面"""
    # 检查是否是管理员
    if session['username'] != 'admin':
        flash('仅管理员可访问后台')
        return redirect(url_for('chat'))

    return render_template('admin.html')

@app.route('/api/upload', methods=['POST'])
@login_required
def upload_file():
    """文件上传API"""
    try:
        # 检查是否是管理员
        if session['username'] != 'admin':
            return jsonify({'error': '仅管理员可上传文件'}), 403

        if 'file' not in request.files:
            return jsonify({'error': '未选择文件'}), 400

        file = request.files['file']

        if file.filename == '':
            return jsonify({'error': '未选择文件'}), 400

        # 验证文件扩展名
        allowed_extensions = {'txt', 'md', 'pdf', 'doc', 'docx', 'json', 'csv', 'xlsx'}
        file_extension = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''

        if file_extension not in allowed_extensions:
            return jsonify({'error': f'不支持的文件类型，仅支持: {", ".join(allowed_extensions)}'}), 400

        # 安全保存文件名
        import os
        import uuid
        from werkzeug.utils import secure_filename

        # 生成唯一文件名
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        upload_path = os.path.join('data', 'knowledge', unique_filename)

        # 保存文件
        file.save(upload_path)

        # 记录上传日志
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO file_uploads (filename, original_name, uploaded_by, file_size) VALUES (%s, %s, %s, %s)",
                (unique_filename, filename, session['username'], os.path.getsize(upload_path))
            )
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"记录上传日志失败: {e}")  # 如果表不存在，忽略错误

        # 调用向量化处理
        try:
            from vector_build import MysqlConnector
            mysql_connector = MysqlConnector()
            mysql_connector.data_opt_add(unique_filename)
            print(f"✅ 文件 {filename} 向量化处理完成")
        except Exception as e:
            print(f"⚠️ 文件向量化失败: {str(e)}")
            # 向量化失败不影响文件上传成功，但记录错误信息

        return jsonify({
            'success': True,
            'message': '文件上传成功',
            'filename': unique_filename,
            'original_name': filename
        })

    except Exception as e:
        print(f"文件上传失败: {str(e)}")
        return jsonify({'error': f'文件上传失败: {str(e)}'}), 500

@app.route('/api/files')
@login_required
def list_files():
    """获取已上传文件列表"""
    try:
        # 检查是否是管理员
        if session['username'] != 'admin':
            return jsonify({'error': '仅管理员可查看文件列表'}), 403

        import os
        knowledge_dir = os.path.join('data', 'knowledge')
        files = []

        if os.path.exists(knowledge_dir):
            for filename in os.listdir(knowledge_dir):
                file_path = os.path.join(knowledge_dir, filename)
                if os.path.isfile(file_path):
                    files.append({
                        'name': filename,
                        'size': os.path.getsize(file_path),
                        'upload_time': os.path.getctime(file_path)
                    })

        # 按上传时间排序
        files.sort(key=lambda x: x['upload_time'], reverse=True)

        return jsonify({'files': files})

    except Exception as e:
        print(f"获取文件列表失败: {str(e)}")
        return jsonify({'error': f'获取文件列表失败: {str(e)}'}), 500

@app.route('/api/download/<filename>')
@login_required
def download_file(filename):
    """文件下载API"""
    try:
        # 检查是否是管理员
        if session['username'] != 'admin':
            return jsonify({'error': '仅管理员可下载文件'}), 403

        import os
        from werkzeug.utils import safe_join
        from flask import send_file

        # 安全验证文件名
        if '..' in filename or filename.startswith('/'):
            return jsonify({'error': '无效的文件名'}), 400

        file_path = safe_join('data', 'knowledge', filename)

        if not os.path.exists(file_path):
            return jsonify({'error': '文件不存在'}), 404

        # 创建下载文件名（去掉UUID前缀）
        original_name = '_'.join(filename.split('_')[1:]) if '_' in filename else filename

        return send_file(
            file_path,
            as_attachment=True,
            download_name=original_name
        )

    except Exception as e:
        print(f"文件下载失败: {str(e)}")
        return jsonify({'error': f'文件下载失败: {str(e)}'}), 500

@app.route('/api/delete/<filename>', methods=['DELETE'])
@login_required
def delete_file(filename):
    """文件删除API"""
    try:
        # 检查是否是管理员
        if session['username'] != 'admin':
            return jsonify({'error': '仅管理员可删除文件'}), 403

        import os
        from werkzeug.utils import safe_join

        # 安全验证文件名
        if '..' in filename or filename.startswith('/'):
            return jsonify({'error': '无效的文件名'}), 400

        file_path = safe_join('data', 'knowledge', filename)

        if not os.path.exists(file_path):
            return jsonify({'error': '文件不存在'}), 404

        # 先记录原文件名用于向量数据库删除
        original_name = '_'.join(filename.split('_')[1:]) if '_' in filename else filename

        # 删除文件
        os.remove(file_path)

        # 删除向量数据库中的对应数据
        try:
            from vector_build import MysqlConnector
            mysql_connector = MysqlConnector()
            deleted_count = mysql_connector.data_opt_delete(filename)  # 使用唯一文件名
            print(f"🗑️ 已从向量数据库删除 {deleted_count} 条与文件 '{filename}' 相关的记录")
        except Exception as e:
            print(f"⚠️ 向量数据库删除失败: {str(e)}")
            # 向量删除失败不影响文件删除成功，但记录错误信息

        # 记录删除日志
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM file_uploads WHERE filename = %s",
                (filename,)
            )
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"记录删除日志失败: {e}")  # 如果表不存在，忽略错误

        return jsonify({'success': True, 'message': f'文件删除成功，已清理相关向量数据'})

    except Exception as e:
        print(f"文件删除失败: {str(e)}")
        return jsonify({'error': f'文件删除失败: {str(e)}'}), 500

if __name__ == '__main__':
    import sys
    port = 5000
    if len(sys.argv) > 1 and sys.argv[1] == '--port':
        if len(sys.argv) > 2:
            port = int(sys.argv[2])
    app.run(host='0.0.0.0', port=port)