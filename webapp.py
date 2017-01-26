from flask import Flask, url_for, flash, redirect, render_template, request
from model import *
from flask import session as login_session
from flask import g
import locale

app = Flask(__name__)
app.secret_key = "MY_SUPER_SECRET_KEY"

engine = create_engine('sqlite:///fizzBuzz.db')
Base.metadata.bind = engine
DBSession = sessionmaker(bind=engine, autoflush=False)
session = DBSession()

@app.route('/')
@app.route('/inventory')
def inventory():
	items=session.query(Product).all()
	return render_template("inventory.html", items=items)

@app.route('/login', methods = ['GET', 'POST'])
def login():
	if request.method == 'GET':
		return render_template('login.html')
	elif request.method=='POST':
		email=request.form['email']
		password=request.form['password']
		if email is None or password is None:
			flash('Missing Arguement')
			return redirect(url_for(login))
		if verify_password(email, password):
			customer=session.query(Customer).filter_by(email=email).one()
			flash('Login Successful, welcome, %s' % customer.name)
			login_session['name']=customer.name
			login_session['email']=customer.email
			login_session['id']=customer.id
			return redirect(url_for('inventory'))
		else:
			flash("Incorrect username/password combination")
			return redirect(url_for('login'))

def verify_password(email, password):
	customer= session.query(Customer).filter_by(email=email).first()
	if not customer or not customer.verify_password(password):
		return False
	g.customer=customer
	return True

@app.route('/newCustomer', methods = ['GET','POST'])
def newCustomer():
	if request.method == 'POST':
		name = request.form['name']
		email = request.form['email']
		password = request.form['password']
		address = request.form['address']
		if name is None or email is None or password is None:
			flash("Your form is missing arguments")
			return redirect(url_for('newCustomer'))
		if session.query(Customer).filter_by(email = email).first() is not None:
			flash("A user with this email address already exists")
			return redirect(url_for('newCustomer'))
		customer = Customer(name = name, email=email, address = address)
		customer.hash_password(password)
		session.add(customer)
		shoppingCart = ShoppingCart(customer=customer)
		session.add(shoppingCart)
		session.commit()
		flash("User Created Successfully!")
		return redirect(url_for('inventory'))
	else:
		return render_template('newCustomer.html')


@app.route("/product/<int:product_id>")
def product(product_id):
	product=session.query(Product).filter_by(id=product_id).one()
	return render_template('product.html', product=product)

@app.route("/product/<int:product_id>/addToCart", methods = ['POST'])
def addToCart(product_id):
	if 'id' not in login_session:
		flash("You must be logged in to perform this action")
		return redirect(url_for('login'))
	quantity=request.form['quantity']
	product=session.query(Product).filter_by(id=product_id).one()
	shoppingCart=session.query(ShoppingCart).filter_by(customer_id=login_session['id']).one()
	if product.name in [item.product.name for item in shoppingCart.products]:
		assoc=session.query(ShoppingCartAssociation).filter_by(shoppingCart=shoppingCart).filter_by(product=product).one()
		assoc.quantity=int(assoc.quantity)+int(quantity)
		flash("Successfully added to Shopping Cart")
		return redirect(url_for('shoppingCart'))
	else:
		a=ShoppingCartAssociation(product=product, quantity=quantity)
		shoppingCart.products.append(a)
		session.add_all([a, product, shoppingCart])
		session.commit()
		flash("Successfully added to Shopping Cart")
		return redirect(url_for('shoppingCart'))

@app.route("/shoppingCart")
def shoppingCart():
	if 'id' not in login_session:
		flash("You must be logged in to perform this action")
		return redirect(url_for('login'))
	shoppingCart=session.query(ShoppingCart).filter_by(customer_id=login_session['id']).one()
	return render_template('shoppingCart.html', shoppingCart=shoppingCart)

@app.route("/removeFromCart/<int:product_id>", methods = ['POST'])
def removeFromCart(product_id):
	if 'id' not in login_session:
		flash("You must be logged in to perform this action")
		return redirect(url_for('login'))
	shoppingCart=session.query(ShoppingCart).filter_by(customer_id=login_session['id']).one()
	association=session.query(ShoppingCartAssociation).filter_by(shoppingCart=shoppingCart).filter_by(product_id=product_id).one()
	session.delete(association)
	session.commit()
	flash("Item deleted successfully")
	return redirect(url_for('shoppingCart'))

@app.route("/updateQuantity/<int:product_id>", methods = ['POST'])
def updateQuantity(product_id):
	if 'id' not in login_session:
		flash("You must be logged in to perform this action")
		return redirect(url_for('login'))
	quantity=request.form["quantity"]
	if quantity==0:
		return removeFromCart(product_id)
	if quantity<0:
		flash("Can't store negative quantities because that would be silly.")
		return redirect(url_for('shoppingCart'))
	shoppingCart=session.query(ShoppingCart).filter_by(customer_id=login_session['id']).one()
	assoc=session.query(ShoppingCartAssociation).filter_by(shoppingCart=shoppingCart).filter_by(product_id=product_id).one()
	assoc.quantity=quantity
	session.add(assoc)
	session.commit()
	flash("Quantity Updated Successfully")
	return redirect(url_for('shoppingCart'))

@app.route("/checkout", methods = ['GET', 'POST'])
def checkout():
	if 'id' not in login_session:
		flash("You must be logged in to perform this action")
		return redirect(url_for('login'))
	shoppingCart = session.query(ShoppingCart).filter_by(customer_id=login_session['id']).one()
	if request.method== 'POST':
		order=Order(customer_id=login_session['id'], confirmation=generateConfirmationNumber())
		order.total=calculateTotal(shoppingCart)
		for item in shoppingCart.products:
			assoc=OrdersAssociation(product=item.product, product_qty=item.quantity)
			order.products.append(assoc)
			session.delete(item)
		session.add_all([order, shoppingCart])
		session.commit()
		return redirect(url_for('confirmation', confirmation=order.confirmation))
	elif request.method=='GET':
		return render_template('checkout.html', shoppingCart=shoppingCart, total="%.2f" % calculateTotal(shoppingCart))

def calculateTotal(shoppingCart):
	total=0.0
	for item in shoppingCart.products:
		price=item.product.price.strip('$')
		total+=item.quantity * float(price)
	return total

def generateConfirmationNumber():
	return "".join(random.choice(string.ascii_uppercase + string.digits) for x in xrange(16))

@app.route("/confirmation/<confirmation>")
def confirmation(confirmation):
	if 'name' not in login_session:
		flash("You must be logged in to perform this action")
		return redirect(url_for('login'))
	order=session.query(Order).filter_by(confirmation=confirmation).one()
	return render_template('confirmation.html', order=order)

@app.route('/logout', methods = ['GET'])
def logout():
	if 'id' not in login_session:
		flash("You must be logged in order to log out")
		return redirect(url_for('login'))
	del login_session['name']
	del login_session['email']
	del login_session['id']
	flash("Logged Out Successfully")
	return redirect(url_for('inventory'))



if __name__ == '__main__':
	app.run(debug=True)
