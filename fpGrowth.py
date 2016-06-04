import pandas as pd
import itertools


from collections import defaultdict, namedtuple

def find_frequent_itemsets(df, minimum_support, include_support=False):
    """
    Find frequent itemsets in the given transactions using FP-growth. This
    function returns a generator instead of an eagerly-populated list of items.

    The `transactions` parameter can be any iterable of iterables of items.
    `minimum_support` should be an integer specifying the minimum number of
    occurrences of an itemset for it to be accepted.

    Each item must be hashable (i.e., it must be valid as a member of a
    dictionary or a set).

    If `include_support` is true, yield (itemset, support) pairs instead of
    just the itemsets.
    """
    y = df.columns
    x = df.apply(lambda x: x>0, raw=True)
    z=x.apply(lambda x: list(y[x.values]), axis=1)

    master = FPTree()
    for n in range(1,len(z)):
       master.add(z[n])


    def find_with_suffix(tree, suffix):
        for item, nodes in tree.items():
            support = sum(n.count for n in nodes)
            if support >= minimum_support and item not in suffix:
                # New winner!
                found_set = [item] + suffix
                yield (found_set, support) if include_support else found_set

                # Build a conditional tree and recursively search for frequent
                # itemsets within it.
                cond_tree = conditional_tree_from_paths(tree.prefix_paths(item))
                for s in find_with_suffix(cond_tree, found_set):
                    yield s # pass along the good news to our caller

    # Search for frequent itemsets, and yield the results we find.
    for itemset in find_with_suffix(master, []):
        yield itemset

class FPTree(object):
    """
    An FP tree.

    This object may only store transaction items that are hashable
    (i.e., all items must be valid as dictionary keys or set members).
    """

    Route = namedtuple('Route', 'head tail')

    def __init__(self):
        # The root node of the tree.
        self._root = FPNode(self, None, None)

        # A dictionary mapping items to the head and tail of a path of
        # "neighbors" that will hit every node containing that item.
        self._routes = {}


    @property
    def root(self):
        """The root node of the tree."""
        return self._root

    def add(self, transaction):
        """Add a transaction to the tree."""
        point = self._root

        for item in transaction:
            next_point = point.search(item)
            if next_point:
                # There is already a node in this tree for the current
                # transaction item; reuse it.
                next_point.increment()
            else:
                # Create a new point and add it as a child of the point we're
                # currently looking at.
                next_point = FPNode(self, item)
                point.add(next_point)

                # Update the route of nodes that contain this item to include
                # our new node.
                self._update_route(next_point)

            point = next_point

    def _update_route(self, point):
        """Add the given node to the route through all nodes for its item."""
        assert self is point.tree

        try:
            route = self._routes[point.item]
            route[1].neighbor = point # route[1] is the tail
            self._routes[point.item] = self.Route(route[0], point)
        except KeyError:
            # First node for this item; start a new route.
            self._routes[point.item] = self.Route(point, point)

    def items(self):
        """
        Generate one 2-tuples for each item represented in the tree. The first
        element of the tuple is the item itself, and the second element is a
        generator that will yield the nodes in the tree that belong to the item.
        """
        for item in self._routes.keys():
            yield (item, self.nodes(item))

    def nodes(self, item):
        """
        Generate the sequence of nodes that contain the given item.
        """

        try:
            node = self._routes[item][0]
        except KeyError:
            return

        while node:
            yield node
            node = node.neighbor

    def prefix_paths(self, item):
        """Generate the prefix paths that end with the given item."""

        def collect_path(node):
            path = []
            while node and not node.root:
                path.append(node)
                node = node.parent
            path.reverse()
            return path

        return (collect_path(node) for node in self.nodes(item))

def conditional_tree_from_paths(paths):
    """Build a conditional FP-tree from the given prefix paths."""
    tree = FPTree()
    condition_item = None
    items = set()

    # Import the nodes in the paths into the new tree. Only the counts of the
    # leaf notes matter; the remaining counts will be reconstructed from the
    # leaf counts.
    for path in paths:
        if condition_item is None:
            condition_item = path[-1].item

        point = tree.root
        for node in path:
            next_point = point.search(node.item)
            if not next_point:
                # Add a new node to the tree.
                items.add(node.item)
                count = node.count if node.item == condition_item else 0
                next_point = FPNode(tree, node.item, count)
                point.add(next_point)
                tree._update_route(next_point)
            point = next_point

    assert condition_item is not None

    # Calculate the counts of the non-leaf nodes.
    for path in tree.prefix_paths(condition_item):
        count = path[-1].count
        for node in reversed(path[:-1]):
            node._count += count

    return tree

class FPNode(object):
    """A node in an FP tree."""

    def __init__(self, tree, item, count=1):
        self._tree = tree
        self._item = item
        self._count = count
        self._parent = None
        self._children = {}
        self._neighbor = None

    def add(self, child):
        """Add the given FPNode `child` as a child of this node."""

        if not isinstance(child, FPNode):
            raise TypeError("Can only add other FPNodes as children")

        if not child.item in self._children:
            self._children[child.item] = child
            child.parent = self

    def search(self, item):
        """
        Check whether this node contains a child node for the given item.
        If so, that node is returned; otherwise, `None` is returned.
        """
        try:
            return self._children[item]
        except KeyError:
            return None

    def __contains__(self, item):
        return item in self._children

    @property
    def tree(self):
        """The tree in which this node appears."""
        return self._tree

    @property
    def item(self):
        """The item contained in this node."""
        return self._item

    @property
    def count(self):
        """The count associated with this node's item."""
        return self._count

    def increment(self):
        """Increment the count associated with this node's item."""
        if self._count is None:
            raise ValueError("Root nodes have no associated count.")
        self._count += 1

    @property
    def root(self):
        """True if this node is the root of a tree; false if otherwise."""
        return self._item is None and self._count is None

    @property
    def leaf(self):
        """True if this node is a leaf in the tree; false if otherwise."""
        return len(self._children) == 0

    @property
    def parent(self):
        """The node's parent"""
        return self._parent

    @parent.setter
    def parent(self, value):
        if value is not None and not isinstance(value, FPNode):
            raise TypeError("A node must have an FPNode as a parent.")
        if value and value.tree is not self.tree:
            raise ValueError("Cannot have a parent from another tree.")
        self._parent = value

    @property
    def neighbor(self):
        """
        The node's neighbor; the one with the same value that is "to the right"
        of it in the tree.
        """
        return self._neighbor

    @neighbor.setter
    def neighbor(self, value):
        if value is not None and not isinstance(value, FPNode):
            raise TypeError("A node must have an FPNode as a neighbor.")
        if value and value.tree is not self.tree:
            raise ValueError("Cannot have a neighbor from another tree.")
        self._neighbor = value

    @property
    def children(self):
        """The nodes that are children of this node."""
        return tuple(self._children.itervalues())

    def inspect(self, depth=0):
        print ('  ' * depth) + repr(self)
        for child in self.children:
            child.inspect(depth + 1)

    def __repr__(self):
        if self.root:
            return "<%s (root)>" % type(self).__name__
        return "<%s %r (%r)>" % (type(self).__name__, self.item, self.count)


def main():

    #Reading csv file
    data=pd.read_csv("groceries.csv")

    #Removing duplicate items in a transaction
    data = data.drop_duplicates(subset=['Person', 'item'], keep='last')

    #All items are bought only once as the duplicates are removed.
    data["Quantity"]=1

    #Converting data from long to wide format
    dataWide=data.pivot("Person", "item", "Quantity")

    #Replace NA with 0
    dataWide.fillna(0, inplace=True)
    #print(dataWide.head())

    data_purchases = dataWide.copy()

    #To make the 'Person' field just another column and not an index
    data_purchases = data_purchases.reset_index()

    data_purchases = data_purchases.drop("Person", axis=1)

    #Finding support of items
    support=data_purchases.sum(axis=0)
    #print(support['UHT-milk'])

    #Setting min support
    minsupport=100

    #Converting pandas series to dict
    support=support.to_dict()

    #Find infrequent items(support<minsupport)
    infrequent = dict((item, support) for item, support in support.items()
        if support < minsupport)

    #Infrequent Columnss
    infreq=list(item for item,support in infrequent.items())

    #Dropping infrequent columns
    data_purchases=data_purchases.drop(infreq, axis=1)

    #Find frequent items(support>=minsupport)
    frequent = dict((item, support) for item, support in support.items()
        if support >= minsupport)

    #Sorting Columns based on support
    frequent=dict(sorted(frequent.items(), key=lambda x: x[1],reverse=True))

    #Frequent Columnss
    freq=list(item for item,support in frequent.items())

    data_purchases=data_purchases[freq]

    freqItemsets=find_frequent_itemsets(data_purchases,minsupport, True)
    generateRules(freqItemsets)

def generateRules(freqItemsets):
    result=[]
    for itemset, support in freqItemsets:
        if len(itemset)>1:
            result.append((itemset,support))

        result = sorted(result, key=lambda i: i[0])

        for itemset, support in result:

            results = list(powerset(itemset))
            results.remove(())


            for subset in itertools.combinations(results, 2):
                t=(subset[0],' --> ',subset[1],'\tsupport:',support)

                with open("Output.txt", "a") as text_file:
                    line = ' '.join(str(x) for x in t)
                    text_file.write(line + '\n')
                    #print('writing')





from itertools import chain, combinations

def powerset(iterable):
    "powerset([1,2,3]) --> () (1,) (2,) (3,) (1,2) (1,3) (2,3) (1,2,3)"
    s = list(iterable)
    return chain.from_iterable(combinations(s, r) for r in range(len(s)+1))


if __name__ == '__main__':
    main()
'''

rows=data_purchases.iterrows
rows=pd.DataFrame(rows)
for row in rows:
        for column in range(0,len(data_purchases.columns)):
                if data_purchases[column][row]>0:
                        print(column)

print(data_purchases.astype(bool).sum(axis=1))

cols=[]
data_purchases.apply(lambda x: x > 0, raw=True).apply(lambda x: list(cols[x.values]), axis=1)
print(cols)


frequent={k: v for k, v in support.items if v>minsupport}
print(frequent)

for row in data_purchases.iterrows:
    print(row)
'''