import os
import sys
import optparse
import getpass

import MySQLdb as mysql

USAGE = "usage: %prog database_name [options]"
def build_options():
    parser = optparse.OptionParser(usage=USAGE)
    parser.add_option('-t', '--tmp_db',
                      dest='tmp_db',
                      default='::memory::',
                      help="Path to temporary database to use.  Default memory.")

    parser.add_option('-u', '--user',
                      dest='user',
                      default=getpass.getuser(),
                      help="User to perform migration as")
    
    parser.add_option('-p', '--password',
                      dest='password',
                      help="Password to use.  If none, asks for user input.")

    parser.add_option('-H', '--host',
                      dest='host',
                      default='localhost',
                      help="Host for mysql database")

    parser.add_option('-P', '--port',
                      dest='port',
                      default=3306,
                      help="Port to use")

    parser.add_option('-b', '--backup_path',
                      dest='backup',
                      default='backup.sql',
                      help="Which file to use for backing up the database.  Default is 'backup.db'")

    return parser

class Credentials(object):
    def __init__(self, opts):
        self.user = opts.user
        self.password = opts.password
        if not self.password:
            self.password = getpass.getpass()

        self.host = opts.host
        self.port = int(opts.port) if opts.port else None

    def to_commandline(self):
        args = []
        if self.user:
            args.append('-u%s' % self.user)

        if self.password:
            args.append('-p%s' % self.password)

        if self.host:
            args.append('-h%s' % self.host)

        if self.port:
            args.append('-P%i' % self.port)

        return ' '.join(args)

    def connection(self, database):
        return mysql.connect(user   = self.user,
                             passwd = self.password,
                             host   = self.host,
                             port   = self.port,
                             db     = database)


def backup_database(credentials, database, path):
    print "Backing up database %s to %s..." % (database, path)
    if os.path.exists(path):
        print "File already exists at %s.  As a precaution, exiting..." % path
        sys.exit(2)

    retcode = os.system('mysqldump %s %s --databases --add-drop-database > %s' % (credentials.to_commandline(), database, path))
    if retcode:
        print 'Database dump failed!  Exited with status code %i' % (retcode >> 8)
        sys.exit(2)

    print "Database dump completed successfully."
    os.system('less %s' % path)
    results = raw_input("Press 'y' to continue after confirming the backup is correct: ") 
    if results.lower() != 'y':
        print "Exiting..."
        sys.exit(0)

get_break_line = lambda s: '-' * max(map(len, s.split('\n')))

def execute_sql(statements):
    def _execute_sql(connection, commit=True):
        c = connection.cursor()
        for sql in statements:
            print "Executing statment:"
            break_line = get_break_line(sql)
            print break_line
            print sql
            c.execute(sql)
            print break_line

        if commit:
            connection.commit()
    
    return _execute_sql

NEW_TABLES_SQL = [
"""
CREATE TABLE `cropduster_image_meta` (
    `id` integer AUTO_INCREMENT NOT NULL PRIMARY KEY,
    `attribution` varchar(255),
    `attribution_link` varchar(255),
    `caption` varchar(255)
)
""",
"""
CREATE TABLE `cropduster_image_size_sets` (
    `id` integer AUTO_INCREMENT NOT NULL PRIMARY KEY,
    `image_id` integer NOT NULL,
    `sizeset_id` integer NOT NULL,
    UNIQUE (`image_id`, `sizeset_id`)
)
""",
]

create_new_tables = execute_sql(NEW_TABLES_SQL)

NEW_COLUMNS_SQL = [
"""
ALTER TABLE `cropduster_size` ADD COLUMN (
    `date_modified` datetime,
    `retina` bool NOT NULL
)
""",
"""
ALTER TABLE `cropduster_image` ADD COLUMN (
    `original_id` integer,
    `size_id` integer,
    `crop_id` integer UNIQUE,
    `metadata_id` integer,
    `date_modified` datetime,
    `width` integer UNSIGNED,
    `height` integer UNSIGNED
)
""",
]
add_new_columns = execute_sql(NEW_COLUMNS_SQL)

COPY_DATA_SQL_1 = [
# Copy the metadata from images into metadata
"""
INSERT INTO `cropduster_image_meta` 
    (`id`,`attribution`, `caption`)
    SELECT `id`, `attribution`, `caption` FROM
        `cropduster_image`
    ORDER BY `id` DESC
""",
# Copy the metadata foreign key over to the metadata_id field.
"""
UPDATE `cropduster_image` 
    SET cropduster_image.metadata_id = cropduster_image.id
""",
]

# Update the auto increment for the metadata table
ALTER_META_AUTO_INCREMENT = \
"""
ALTER TABLE `cropduster_image_meta` AUTO_INCREMENT = %s
"""

MAX_META_ID = \
"""(SELECT MAX(`id`)+1 from `cropduster_image_meta`)"""


COPY_DATA_SQL_3 = [
# Copy linked size sets into join table
"""
INSERT INTO `cropduster_image_size_sets`
    (`image_id`, `sizeset_id`)
    SELECT `id`, `size_set_id` FROM
        `cropduster_image`
""",

# Copy derived images  into image table.
"""
INSERT INTO `cropduster_image`
    (`original_id`, `size_set_id`, `size_id`, `metadata_id`, `image`, `crop_id`, `date_modified`)
SELECT i.id `original_id`, ss.id size_set_id, s.id size_id, i.metadata_id `metadata_id`, '' `image`, c.id crop_id, SYSDATE() `date_modified`
    FROM `cropduster_image` i
    INNER JOIN `cropduster_sizeset` ss ON ss.id = i.size_set_id
    INNER JOIN `cropduster_size` s ON s.size_set_id = ss.id
    LEFT JOIN `cropduster_crop` c on (c.size_id = s.id and c.image_id = i.id)
"""
]

copy_data_1 = execute_sql(COPY_DATA_SQL_1)
copy_data_3 = execute_sql(COPY_DATA_SQL_3)
def copy_data(connection):
    """
    Broken out due to the alter statement requiring explicit value.
    """
    copy_data_1(connection, False)

    c = connection.cursor()
    print MAX_META_ID
    c.execute(MAX_META_ID)
    max_id = c.fetchone()[0]

    c.execute(ALTER_META_AUTO_INCREMENT, [max_id])
    print ALTER_META_AUTO_INCREMENT

    copy_data_3(connection)

ALTER_TABLES_SQL = [

# Cleanup image.
"""
ALTER TABLE `cropduster_image` 
    DROP FOREIGN KEY `size_set_id_refs_id_ecb90bef`
""",
"""
ALTER TABLE `cropduster_image` 
    DROP COLUMN `size_set_id`,
    DROP COLUMN `attribution`,
    DROP COLUMN `caption`
""",

# Cleanup size
"""
ALTER TABLE `cropduster_size`
    CHANGE `auto_size` `auto_crop` bool NOT NULL
""",

# Cleanup crop
"""
ALTER TABLE `cropduster_crop`
    DROP FOREIGN KEY `size_id_refs_id_5bb0c7d2`
""",
"""
ALTER TABLE `cropduster_crop`
    DROP COLUMN `size_id`
""",
"""
ALTER TABLE `cropduster_crop`
    DROP FOREIGN KEY `image_id_refs_id_307faed1`
""",
"""
ALTER TABLE `cropduster_crop`
    DROP COLUMN `image_id`
""",

]
alter_tables = execute_sql(ALTER_TABLES_SQL)

FOREIGN_KEY_SQL = [
# Add foreign keys to image
"""
ALTER TABLE `cropduster_image` 
    ADD CONSTRAINT `metadata_id_refs_id_9ca83b9c` 
        FOREIGN KEY (`metadata_id`) 
        REFERENCES `cropduster_image_meta` (`id`)
""",
"""
ALTER TABLE `cropduster_image` 
    ADD CONSTRAINT `crop_id_refs_id_689dabf1` 
        FOREIGN KEY (`crop_id`) 
        REFERENCES `cropduster_crop` (`id`)
""",
"""
ALTER TABLE `cropduster_image` 
    ADD CONSTRAINT `size_id_refs_id_78edea90` 
        FOREIGN KEY (`size_id`) 
        REFERENCES `cropduster_size` (`id`)
""",
"""
ALTER TABLE `cropduster_image` 
    ADD CONSTRAINT `original_id_refs_id_9af2fc1b` 
        FOREIGN KEY (`original_id`) 
        REFERENCES `cropduster_image` (`id`)
""",

# Add foreign keys to size
#"""
#ALTER TABLE `cropduster_size` 
#    ADD CONSTRAINT `size_set_id_refs_id_78fda80a` 
#        FOREIGN KEY (`size_set_id`) 
#        REFERENCES `cropduster_sizeset` (`id`)
#""",

# Add foreign keys to image size sets
"""
ALTER TABLE `cropduster_image_size_sets` 
    ADD CONSTRAINT `sizeset_id_refs_id_f06e2d33` 
        FOREIGN KEY (`sizeset_id`) 
        REFERENCES `cropduster_sizeset` (`id`)
""",
"""
ALTER TABLE `cropduster_image_size_sets` 
    ADD CONSTRAINT `image_id_refs_id_f3fb53b1` 
        FOREIGN KEY (`image_id`) 
        REFERENCES `cropduster_image` (`id`)
""",

]

add_foreign_keys = execute_sql(FOREIGN_KEY_SQL)

ADD_INDEX_SQL = [
#"""CREATE INDEX `cropduster_sizeset_52094d6e` ON `cropduster_sizeset` (`name`)""",
#"""CREATE INDEX `cropduster_size_5f278936` ON `cropduster_size` (`size_set_id`)""",
#"""CREATE INDEX `cropduster_size_52094d6e` ON `cropduster_size` (`name`)""",
#"""CREATE INDEX `cropduster_size_a951d5d6` ON `cropduster_size` (`slug`)""",
"""CREATE INDEX `cropduster_image_533ede81` ON `cropduster_image` (`original_id`)""",
"""CREATE INDEX `cropduster_image_6154b20f` ON `cropduster_image` (`size_id`)""",
"""CREATE INDEX `cropduster_image_f51cb081` ON `cropduster_image` (`metadata_id`)""",
]

add_indexes = execute_sql(ADD_INDEX_SQL)

OPTIMIZE_TABLES = [
"""OPTIMIZE TABLE `cropduster_image`""",
"""OPTIMIZE TABLE `cropduster_size`""",
"""OPTIMIZE TABLE `cropduster_sizeset`""",
"""OPTIMIZE TABLE `cropduster_image_size_sets`""",
"""OPTIMIZE TABLE `cropduster_image`""",
"""OPTIMIZE TABLE `cropduster_crop`""",
]

optimize_tables = execute_sql(OPTIMIZE_TABLES)

def main():
    parser = build_options()
    options, args = parser.parse_args()

    if len(args) != 1:
        parser.print_usage()
        sys.exit(1)

    database = args[0]

    creds = Credentials(options)

    # 1. Backup the database.  This is a sanity check, the developer should already have
    # a backup.
    backup_database(creds, database, options.backup)
    
    # Get the connection
    conn = creds.connection(database)

    # set storage engine
    conn.cursor().execute("set storage_engine=INNODB")

    # 2. Create new tables.
    print "Creating new tables..."
    create_new_tables(conn)

    # 3. Add new columns to existing tables.
    print "Adding columns to existing tables..."
    add_new_columns(conn)

    # 4. Copy data into new tables.
    print "Copying data into new tables..."
    copy_data(conn)

    # 5. Delete/alter columns from current tables.
    print "Deleting/altering columns from current tables..."
    alter_tables(conn)

    # 6. Update foreign keys.
    print "Updating foreign keys..."
    add_foreign_keys(conn)

    # 7. Add indexes to new and existing tables.
    print "Adding indexes..."
    add_indexes(conn)

    # 8. Optimize
    print "Optimizing tables..."
    optimize_tables(conn)
    print "Finished!"

if __name__ == '__main__':
    main()
